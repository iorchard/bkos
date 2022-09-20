"""A TACO2 Provisioning Pulumi Program"""
# pylint: disable=C0103
import os

import pulumi
import pulumi_openstack as openstack
import pulumi_random as random
import pulumi_command as command

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from jinja2 import Environment
from jinja2 import FileSystemLoader

import utils

config = pulumi.Config()
os_config = pulumi.Config("openstack")

cluster_name = config.get("cluster_name")

os.makedirs(name=f".{cluster_name}", mode=0o755, exist_ok=True)
private_file = f".{cluster_name}/{cluster_name}"
public_file = f"{private_file}" + ".pub"
if not (os.path.isfile(private_file) and os.path.isfile(public_file)):
    key = rsa.generate_private_key(
        backend=default_backend(), public_exponent=65537, key_size=2048
    )
    private_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    public_key = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
        )
        .decode("utf-8")
    )
    with open(file=private_file, mode="w", encoding="ascii") as f:
        f.write(private_key)
        os.chmod(path=private_file, mode=0o600)
    with open(file=public_file, mode="w", encoding="ascii") as f:
        f.write(public_key)
        os.chmod(path=public_file, mode=0o644)
else:
    # get private/public key
    with open(file=private_file, mode="r", encoding="ascii") as f:
        private_key = f.read()
    with open(file=public_file, mode="r", encoding="ascii") as f:
        public_key = f.read()

parent_project = openstack.identity.get_project(name=os_config.get('tenantName'))
project = openstack.identity.Project(
    "project",
    name=f"{cluster_name}",
    description=f"{cluster_name} Project",
    parent_id=parent_project.id,
)

# create random password
adminpw = random.RandomPassword(
    "adminpw", length=20, upper=True, number=True, special=False
)
memberpw = random.RandomPassword(
    "memberpw", length=20, upper=True, number=True, special=False
)
readerpw = random.RandomPassword(
    "readerpw", length=20, upper=True, number=True, special=False
)
adminpw.result.apply(lambda v: utils.write_to_file(".adminpw", "w", f"{v}", 0o600))
memberpw.result.apply(lambda v: utils.write_to_file(".memberpw", "w", f"{v}", 0o600))
readerpw.result.apply(lambda v: utils.write_to_file(".readerpw", "w", f"{v}", 0o600))

# create admin user in the project
admin_user = openstack.identity.User(
    "admin_user",
    name=f"{cluster_name}_admin",
    default_project_id=project.id,
    password=adminpw.result,
)
member_user = openstack.identity.User(
    "member_user",
    name=f"{cluster_name}_member",
    default_project_id=project.id,
    password=memberpw.result,
)
reader_user = openstack.identity.User(
    "reader_user",
    name=f"{cluster_name}_reader",
    default_project_id=project.id,
    password=readerpw.result,
)
# get admin role
admin_role = openstack.identity.get_role(name="admin")
member_role = openstack.identity.get_role(name="member")
reader_role = openstack.identity.get_role(name="reader")
# add a role to user
admin_role_assign = openstack.identity.RoleAssignment(
    "admin_role_assign",
    project_id=project.id,
    role_id=admin_role.id,
    user_id=admin_user.id,
)
member_role_assign = openstack.identity.RoleAssignment(
    "member_role_assign",
    project_id=project.id,
    role_id=member_role.id,
    user_id=member_user.id,
)
reader_role_assign = openstack.identity.RoleAssignment(
    "reader_role_assign",
    project_id=project.id,
    role_id=reader_role.id,
    user_id=reader_user.id,
)

# store each rc files
with open(file=".adminpw", mode="r", encoding="ascii") as f:
    s_adminpw = f.read()
with open(file=".memberpw", mode="r", encoding="ascii") as f:
    s_memberpw = f.read()
with open(file=".readerpw", mode="r", encoding="ascii") as f:
    s_readerpw = f.read()

rc = [
    {
        "outfile": f".{cluster_name}/adminrc",
        "username": f"{cluster_name}_admin",
        "pwfile": ".adminpw",
        "password": s_adminpw,
    },
    {
        "outfile": f".{cluster_name}/memberrc",
        "username": f"{cluster_name}_member",
        "pwfile": ".memberpw",
        "password": s_memberpw,
    },
    {
        "outfile": f".{cluster_name}/readerrc",
        "username": f"{cluster_name}_reader",
        "pwfile": ".readerpw",
        "password": s_readerpw,
    },
]
env = Environment(loader=FileSystemLoader("templates/"))
tmpl = env.get_template("rc.j2")
for r in rc:
    content = tmpl.render(
        r, auth_url=os_config.get("authUrl"), project_name=cluster_name
    )
    with open(file=r["outfile"], mode="w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(path=r["outfile"], mode=0o600)
    os.remove(path=r["pwfile"])

# create project admin provider
padmin = openstack.Provider(
    "padmin",
    auth_url=os_config.get("authUrl"),
    project_domain_name="default",
    user_domain_name="default",
    tenant_name=cluster_name,
    user_name=f"{cluster_name}_admin",
    password=admin_user.password,
)

keypair = openstack.compute.keypair.Keypair(
    "keypair",
    name=f"{cluster_name}-key",
    public_key=public_key,
    opts=pulumi.ResourceOptions(provider=padmin),
)

# get provider network resource
provider_network = openstack.networking.get_network(
    name=config.get("provider_network_name"),
    opts=pulumi.InvokeOptions(provider=padmin),
)

# create a router
router = openstack.networking.Router(
    "router",
    name=f"{cluster_name}-router",
    admin_state_up=True,
    external_network_id=provider_network.id,
    opts=pulumi.ResourceOptions(provider=padmin),
)

# create self-service networks
networks = []
subnets = []
i = 0
o_network = config.require_object("network")
port_security_enabled = False
enable_dhcp = True

for n in o_network:
    print(f"name: {n['name']}, cidr: {n['cidr']}")
    if n['name'] == 'provider':
        enable_dhcp = False
    net = openstack.networking.Network(
        f"net-{i}",
        name=f"{cluster_name}-{n['name']}-net",
        admin_state_up=True,
        port_security_enabled=port_security_enabled,
        opts=pulumi.ResourceOptions(provider=padmin),
    )
    networks.append(net)
    subnet = openstack.networking.Subnet(
        f"subnet-{i}",
        name=f"{cluster_name}-{n['name']}-subnet",
        ip_version=4,
        enable_dhcp=enable_dhcp,
        dns_nameservers=["8.8.8.8", "8.8.4.4"],
        cidr=n["cidr"],
        network_id=net.id,
        opts=pulumi.ResourceOptions(provider=padmin),
    )
    subnets.append(subnet)
    router_iface = openstack.networking.RouterInterface(
        f"router_iface-{i}",
        router_id=router.id,
        subnet_id=subnet.id,
        opts=pulumi.ResourceOptions(provider=padmin),
    )
    i += 1

# secgroup
#sg = openstack.networking.SecGroup(
#    "sg",
#    name=f"{cluster_name}-sg",
#    description=f"Security Group for {cluster_name}",
#    opts=pulumi.ResourceOptions(provider=padmin),
#)
#sg_icmp = openstack.networking.SecGroupRule(
#    "sg_icmp",
#    direction="ingress",
#    ethertype="IPv4",
#    protocol="icmp",
#    remote_ip_prefix="0.0.0.0/0",
#    description="Allow incoming icmp",
#    security_group_id=sg.id,
#    opts=pulumi.ResourceOptions(provider=padmin),
#)
#sg_tcp = openstack.networking.SecGroupRule(
#    "sg_tcp",
#    direction="ingress",
#    ethertype="IPv4",
#    protocol="tcp",
#    remote_ip_prefix="0.0.0.0/0",
#    description="Allow incoming tcp",
#    security_group_id=sg.id,
#    opts=pulumi.ResourceOptions(provider=padmin),
#)
#sg_udp = openstack.networking.SecGroupRule(
#    "sg_udp",
#    direction="ingress",
#    ethertype="IPv4",
#    protocol="udp",
#    remote_ip_prefix="0.0.0.0/0",
#    description="Allow incoming udp",
#    security_group_id=sg.id,
#    opts=pulumi.ResourceOptions(provider=padmin),
#)
#sg_ipinip = openstack.networking.SecGroupRule(
#    "sg_ipinip",
#    direction="ingress",
#    ethertype="IPv4",
#    protocol="4",
#    remote_ip_prefix="0.0.0.0/0",
#    description="Allow incoming ipinip protocol",
#    security_group_id=sg.id,
#    opts=pulumi.ResourceOptions(provider=padmin),
#)

image = openstack.images.get_image(name="centos7")

# create flavors
c_flavor_controller = config.require_object("flavor_controller")
controller_flavor = openstack.compute.Flavor(
    "controller-flavor",
    name=f"{cluster_name}-controller-flavor",
    vcpus=c_flavor_controller.get("vcpus"),
    ram=c_flavor_controller.get("ram") * 1024,
    disk=c_flavor_controller.get("disk"),
    is_public=False,
    opts=pulumi.ResourceOptions(provider=padmin),
)
c_flavor_worker = config.require_object("flavor_worker")
worker_flavor = openstack.compute.Flavor(
    "worker-flavor",
    name=f"{cluster_name}-worker-flavor",
    vcpus=c_flavor_worker.get("vcpus"),
    ram=c_flavor_worker.get("ram") * 1024,
    disk=c_flavor_worker.get("disk"),
    is_public=False,
    opts=pulumi.ResourceOptions(provider=padmin),
)
c_flavor_storage = config.require_object("flavor_storage")
storage_flavor = openstack.compute.Flavor(
    "storage-flavor",
    name=f"{cluster_name}-storage-flavor",
    vcpus=c_flavor_worker.get("vcpus"),
    ram=c_flavor_worker.get("ram") * 1024,
    disk=c_flavor_worker.get("disk"),
    is_public=False,
    opts=pulumi.ResourceOptions(provider=padmin),
)
c_flavor_bastion = config.require_object("flavor_bastion")
bastion_flavor = openstack.compute.Flavor(
    "bastion-flavor",
    name=f"{cluster_name}-bastion-flavor",
    vcpus=c_flavor_bastion.get("vcpus"),
    ram=c_flavor_bastion.get("ram") * 1024,
    disk=c_flavor_bastion.get("disk"),
    is_public=False,
    opts=pulumi.ResourceOptions(provider=padmin),
)

# get userdata content
tmpl = env.get_template("userdata.j2")
userdata = tmpl.render({"private_key": private_key, "public_key": public_key})
# create instances
i_ci = 0
i_wi = 0
i_si = 0
ip_addresses = []
for o in config.require_object("instance"):
    print(f"num: {o['num']}, role: {o['role']}")
    if o["role"] == "controller":
        for j in range(o["num"]):
            i_ci += 1
            instance = openstack.compute.Instance(
                f"{o['role']}-instance-{i_ci}",
                name=f"{cluster_name}-{o['role']}-{i_ci}",
                flavor_id=controller_flavor.id,
                key_pair=keypair.id,
                user_data=userdata,
                block_devices=[
                    openstack.compute.InstanceBlockDeviceArgs(
                        source_type="image",
                        destination_type="volume",
                        delete_on_termination=True,
                        volume_size=c_flavor_controller.get("disk"),
                        uuid=image.id,
                    )
                ],
                networks=[
                    openstack.compute.InstanceNetworkArgs(uuid=n.id)
                    for n in networks
                ],
                opts=pulumi.ResourceOptions(
                    provider=padmin,
                    depends_on=[subnet],
                    custom_timeouts=pulumi.CustomTimeouts(create="10m"),
                ),
            )
            ip_addresses.append(
                {"name": instance.name, "ip": instance.networks[1].fixed_ip_v4}
            )
    elif o["role"] == "worker":
        for j in range(o["num"]):
            i_wi += 1
            instance = openstack.compute.Instance(
                f"{o['role']}-instance-{i_wi}",
                name=f"{cluster_name}-{o['role']}-{i_wi}",
                flavor_id=worker_flavor.id,
                key_pair=keypair.id,
                user_data=userdata,
                block_devices=[
                    openstack.compute.InstanceBlockDeviceArgs(
                        source_type="image",
                        destination_type="volume",
                        delete_on_termination=True,
                        volume_size=c_flavor_worker.get("disk"),
                        uuid=image.id,
                    )
                ],
                networks=[
                    openstack.compute.InstanceNetworkArgs(uuid=n.id)
                    for n in networks
                ],
                opts=pulumi.ResourceOptions(
                    provider=padmin,
                    depends_on=[subnet],
                    custom_timeouts=pulumi.CustomTimeouts(create="10m"),
                ),
            )
            ip_addresses.append(
                {"name": instance.name, "ip": instance.networks[1].fixed_ip_v4}
            )
    elif o["role"] == "storage":
        for j in range(o["num"]):
            i_si += 1
            instance = openstack.compute.Instance(
                f"{o['role']}-instance-{i_si}",
                name=f"{cluster_name}-{o['role']}-{i_si}",
                flavor_id=storage_flavor.id,
                key_pair=keypair.id,
                user_data=userdata,
                block_devices=[
                    openstack.compute.InstanceBlockDeviceArgs(
                        source_type="image",
                        destination_type="volume",
                        delete_on_termination=True,
                        volume_size=c_flavor_bastion.get("disk"),
                        uuid=image.id,
                    )
                ],
                networks=[
                    openstack.compute.InstanceNetworkArgs(
                        name=f"{cluster_name}-mgmt-net"
                    ),
                    openstack.compute.InstanceNetworkArgs(
                        name=f"{cluster_name}-storage-net"
                    ),
                ],
                opts=pulumi.ResourceOptions(
                    provider=padmin,
                    depends_on=[subnet],
                    custom_timeouts=pulumi.CustomTimeouts(create="10m"),
                ),
            )
            for oi in range(o["osdnum"]):
                vol = openstack.blockstorage.Volume(
                    f"{o['role']}-vol-{i_si}-{oi}",
                    name=f"{cluster_name}-{o['role']}-vol-{i_si}-{oi}",
                    size=o["osdsize"],
                    opts=pulumi.ResourceOptions(provider=padmin),
                )
                va = openstack.compute.VolumeAttach(
                    f"va-{i_si}-{oi}", instance_id=instance.id, volume_id=vol.id
                )
            ip_addresses.append(
                {"name": instance.name, "ip": instance.networks[0].fixed_ip_v4}
            )

# create bastion host
bastion_instance = openstack.compute.Instance(
    "bastion",
    name=f"{cluster_name}-bastion",
    flavor_id=bastion_flavor.id,
    key_pair=keypair.id,
    user_data=userdata,
    block_devices=[
        openstack.compute.InstanceBlockDeviceArgs(
            source_type="image",
            destination_type="volume",
            delete_on_termination=True,
            volume_size=c_flavor_bastion.get("disk"),
            uuid=image.id,
        )
    ],
    networks=[
        openstack.compute.InstanceNetworkArgs(name=f"{cluster_name}-mgmt-net"),
        openstack.compute.InstanceNetworkArgs(
            name=f"{cluster_name}-storage-net"
        )
    ],
    opts=pulumi.ResourceOptions(
        provider=padmin,
        depends_on=[va],
        custom_timeouts=pulumi.CustomTimeouts(create="10m"),
    ),
)
bastion_fip = openstack.networking.FloatingIp(
    "bastion_fip", pool=config.get("provider_network_name")
)
bastion_fip_assoc = openstack.compute.FloatingIpAssociate(
    "bastion_fip_assoc",
    fixed_ip=bastion_instance.networks[0].fixed_ip_v4,
    floating_ip=bastion_fip.address,
    instance_id=bastion_instance.id,
)
ip_addresses.append(
    {
        "name": bastion_instance.name,
        "ip": bastion_instance.networks[0].fixed_ip_v4,
        "fip": bastion_fip.address,
    }
)
b_ret = utils.create_hosts(ip_addresses)

# templating extra_vars.yml
pulumi.export("ip", ip_addresses)
o_repo = config.require_object("repo")
tmpl = env.get_template("extra-vars.yml.j2")
extra_vars = tmpl.render(
    {
        "pip_repo_url": f"{o_repo['pip']}",
        "pkg_repo_url": f"{o_repo['pkg']}",
        "cluster_name": f"{cluster_name}",
        "ceph_network": f"{o_network[4]['cidr']}"
    }
)
utils.write_to_file("files/extra-vars.yml", "w", extra_vars, 0o644)

wait_sleep = command.local.Command(
    "wait_sleep",
    create=f"sleep {config.get('wait_sleep')}",
    opts=pulumi.ResourceOptions(
        depends_on=[bastion_fip_assoc, bastion_instance]
    ),
)
# run an ansible playbook.
preplay = command.local.Command(
    "preplay",
    create=f"""\
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook \
-i ansible_hosts \
--extra-vars=@tmp_vars \
--private-key {private_file} \
site.yml""",
    opts=pulumi.ResourceOptions(
        depends_on=[wait_sleep],
        custom_timeouts=pulumi.CustomTimeouts(create="30m"),
    ),
)

tacoplay = command.remote.Command(
    "tacoplay",
    connection=command.remote.ConnectionArgs(
        host=bastion_fip.address,
        port=22,
        user="clex",
        private_key=private_key,
    ),
    create="""cd /home/clex/taco && \
              ansible -b -i inventory/cloudpc/hosts.ini -m command \
                -a "yum clean all" all && \
              ansible-playbook -b -i inventory/cloudpc/hosts.ini \
                --extra-vars=@inventory/cloudpc/extra-vars.yml \
                site.yml
""",
    opts=pulumi.ResourceOptions(
        depends_on=[preplay],
        custom_timeouts=pulumi.CustomTimeouts(create="60m")
    )
)
postinst = command.remote.Command(
    "postinst",
    connection=command.remote.ConnectionArgs(
        host=bastion_fip.address,
        port=22,
        user="clex",
        private_key=private_key,
    ),
    create="/home/clex/taco/scripts/postinst.sh",
    opts=pulumi.ResourceOptions(
        depends_on=[tacoplay]
    )
)
ceph_status = command.remote.Command(
    "ceph_status",
    connection=command.remote.ConnectionArgs(
        host=bastion_fip.address,
        port=22,
        user="clex",
        private_key=private_key,
    ),
    create="sudo ceph status",
    opts=pulumi.ResourceOptions(
        depends_on=[postinst]
    )
)
k8s_status = command.remote.Command(
    "k8s_status",
    connection=command.remote.ConnectionArgs(
        host=bastion_fip.address,
        port=22,
        user="clex",
        private_key=private_key,
    ),
    create="kubectl get nodes",
    opts=pulumi.ResourceOptions(
        depends_on=[postinst],
    ),
)

pulumi.export("cluster_name", cluster_name)
pulumi.export("bastion_fip", bastion_fip.address)
pulumi.export("ip", ip_addresses)
pulumi.export("ceph_status", ceph_status.stdout)
pulumi.export("k8s_status", k8s_status.stdout)
pulumi.export("postinst_status", postinst.stdout)
