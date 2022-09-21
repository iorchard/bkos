"""A K8S Provisioning Pulumi Program"""
# pylint: disable=C0103
import os

import pulumi
import pulumi_openstack as openstack
import pulumi_random as random
#import pulumi_command as command

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from jinja2 import Environment
from jinja2 import FileSystemLoader

import utils

config = pulumi.Config()
os_config = pulumi.Config("openstack")

cluster_name = config.get("cluster_name")
o_k8s_tmpl = config.require_object("k8s_template")
o_k8s = config.require_object("k8s")

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

project = openstack.identity.Project(
    "project",
    name=f"{cluster_name}",
    description=f"{cluster_name} Project",
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
adminrc = ''
memberrc = ''
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
    # get rc file content for userdata.j2
    with open(file=r["outfile"], mode="r", encoding="utf-8") as f:
        if r["outfile"] == f".{cluster_name}/adminrc":
            adminrc = f.read()
        elif r["outfile"] == f".{cluster_name}/memberrc":
            memberrc = f.read()

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
    name=f"{cluster_name}_key",
    public_key=public_key,
    opts=pulumi.ResourceOptions(provider=padmin),
)

# get provider network resource
provider_network = openstack.networking.get_network(
    name=config.get("provider_network_name"),
    opts=pulumi.InvokeOptions(provider=padmin),
)

# create flavors
o_flavor_master = config.require_object("flavor_master")
master_flavor = openstack.compute.Flavor(
    "master_flavor",
    name=f"{cluster_name}-master-flavor",
    vcpus=o_flavor_master.get("vcpus"),
    ram=o_flavor_master.get("ram")*1024,
    disk=o_flavor_master.get("disk"),
    is_public=True,
    opts=pulumi.ResourceOptions(provider=padmin),
)
o_flavor_node = config.require_object("flavor_node")
node_flavor = openstack.compute.Flavor(
    "node_flavor",
    name=f"{cluster_name}-node-flavor",
    vcpus=o_flavor_node.get("vcpus"),
    ram=o_flavor_node.get("ram")*1024,
    disk=o_flavor_node.get("disk"),
    is_public=True,
    opts=pulumi.ResourceOptions(provider=padmin),
)
o_flavor_bastion = config.require_object("flavor_bastion")
bastion_flavor = openstack.compute.Flavor(
    "bastion_flavor",
    name=f"{cluster_name}-bastion-flavor",
    vcpus=o_flavor_bastion.get("vcpus"),
    ram=o_flavor_bastion.get("ram")*1024,
    disk=o_flavor_bastion.get("disk"),
    is_public=False,
    opts=pulumi.ResourceOptions(provider=padmin),
)

# templating post_install/coredns_configmap/coredns_append/post_run/userdata
tmpl = env.get_template("post_install.yml.j2")
post_install = tmpl.render({
    "cluster_name": f"{cluster_name}"
})
with open(file="files/post_install.yml", mode="w", encoding="utf-8") as f:
    f.write(post_install)

with open(file="files/coredns_configmap.yml", mode="r", encoding="utf-8") as f:
    coredns_configmap = f.read()

tmpl = env.get_template("coredns_append.yml.j2")
coredns_append = tmpl.render({
    "dns_zone_name": config.get('dns_zone_name'),
    "dns_nameserver": o_k8s_tmpl.get('dns_nameserver'),
})
with open(file="files/coredns_append.yml", mode="w", encoding="utf-8") as f:
    f.write(coredns_append)

tmpl = env.get_template("post_run.sh.j2")
post_run = tmpl.render({
    "k8s_ver": o_k8s_tmpl.get("k8s_ver"),
    "helm_ver": o_k8s_tmpl.get("helm_ver"),
    "cluster_name": config.get("cluster_name"),
})
with open(file="files/post_run.sh", mode="w", encoding="utf-8") as f:
    f.write(post_run)

tmpl = env.get_template("userdata.j2")
userdata = tmpl.render({
    "private_key": private_key,
    "public_key": public_key,
    "openstack_release": config.get("openstack_release"),
    "adminrc": adminrc,
    "memberrc": memberrc,
    "post_install": post_install,
    "coredns_configmap": coredns_configmap,
    "coredns_append": coredns_append,
    "post_run": post_run,
})
with open(file="files/userdata", mode="w", encoding="utf-8") as f:
    f.write(userdata)


# create cluster template
d_k8s_labels = {
    "container_runtime": "containerd",
    "selinux_mode": "disabled",
    "use_podman": "true",
    "master_lb_floating_ip_enabled": o_k8s_tmpl.get('mlb_fip_enabled'),
    "boot_volume_size": o_k8s_tmpl.get('boot_volume_size'),
    "boot_volume_type": o_k8s_tmpl.get('boot_volume_type'),
    "etcd_volume_size": o_k8s_tmpl.get('etcd_volume_size'),
    "etcd_volume_type": o_k8s_tmpl.get('etcd_volume_type'),
    "cinder_csi_enabled": "true",
    "cinder_csi_plugin_tag": f"v{o_k8s_tmpl.get('other_ver')}",
    "cloud_provider_enabled": "true",
    "cloud_provider_tag": f"v{o_k8s_tmpl.get('other_ver')}",
    "k8s_keystone_auth_tag": f"v{o_k8s_tmpl.get('other_ver')}",
    "keystone_auth_enabled": "true",
    "kube_tag": f"v{o_k8s_tmpl.get('k8s_ver')}-rancher1",
    "hyperkube_prefix": "docker.io/rancher/",
    "ingress_controller": "octavia",
    "octavia_ingress_controller_tag": f"v{o_k8s_tmpl.get('other_ver')}",
    "kube_dashboard_enabled": "false",
    "availability_zone": o_k8s_tmpl.get('az'),
}
cluster_tmpl = openstack.containerinfra.ClusterTemplate(
    f"{cluster_name}-template",
    name=f"{cluster_name}-template",
    coe="kubernetes",
    image="fcos",
    keypair_id=keypair.id,
    network_driver=o_k8s_tmpl.get("network_driver"),
    master_flavor=master_flavor.id,
    flavor=node_flavor.id,
    volume_driver=o_k8s_tmpl.get("volume_driver"),
    dns_nameserver=o_k8s_tmpl.get("dns_nameserver"),
    external_network_id=provider_network.id,
    master_lb_enabled=o_k8s_tmpl.get("master_lb_enabled"),
    floating_ip_enabled=o_k8s_tmpl.get("floating_ip_enabled"),
    labels=d_k8s_labels,
    opts=pulumi.ResourceOptions(provider=padmin),
)

cluster = openstack.containerinfra.Cluster(
    f"{cluster_name}",
    name=f"{cluster_name}",
    cluster_template_id=cluster_tmpl.id,
    master_count=o_k8s.get("master_count"),
    node_count=o_k8s.get("node_count"),
    opts=pulumi.ResourceOptions(provider=padmin),
)

## create bastion
# get debian image
bastion_image = openstack.images.get_image(name="debian")
# create secgroup for bastion
sg = openstack.networking.SecGroup(
    "sg",
    name=f"{cluster_name}-bastion-sg",
    description=f"Security Group for {cluster_name}-bastion",
    opts=pulumi.ResourceOptions(provider=padmin),
)
sg_icmp = openstack.networking.SecGroupRule(
    "sg_icmp",
    direction="ingress",
    ethertype="IPv4",
    protocol="icmp",
    remote_ip_prefix="0.0.0.0/0",
    description="Allow incoming icmp",
    security_group_id=sg.id,
    opts=pulumi.ResourceOptions(provider=padmin),
)
sg_tcp = openstack.networking.SecGroupRule(
    "sg_tcp",
    direction="ingress",
    ethertype="IPv4",
    protocol="tcp",
    remote_ip_prefix="0.0.0.0/0",
    description="Allow incoming tcp",
    security_group_id=sg.id,
    opts=pulumi.ResourceOptions(provider=padmin),
)
sg_udp = openstack.networking.SecGroupRule(
    "sg_udp",
    direction="ingress",
    ethertype="IPv4",
    protocol="udp",
    remote_ip_prefix="0.0.0.0/0",
    description="Allow incoming udp",
    security_group_id=sg.id,
    opts=pulumi.ResourceOptions(provider=padmin),
)

bastion_instance = openstack.compute.Instance(
    "bastion",
    name=f"{cluster_name}-bastion",
    flavor_id=bastion_flavor.id,
    key_pair=keypair.id,
    security_groups=[sg.name],
    user_data=userdata,
    block_devices=[
        openstack.compute.InstanceBlockDeviceArgs(
            source_type="image",
            destination_type="volume",
            delete_on_termination=True,
            volume_size=o_flavor_bastion.get("disk"),
            uuid=bastion_image.id,
        )
    ],
    networks=[
        openstack.compute.InstanceNetworkArgs(name=f"{cluster_name}"),
    ],
    opts=pulumi.ResourceOptions(
        provider=padmin,
        depends_on=[cluster],
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

pulumi.export("cluster_name", cluster_name)
pulumi.export("kubeconfig", cluster.kubeconfig)
pulumi.export("api_address", cluster.api_address)
pulumi.export("coe_version", cluster.coe_version)
pulumi.export("container_version", cluster.container_version)
pulumi.export("master_addresses", cluster.master_addresses)
pulumi.export("node_addresses", cluster.node_addresses)
pulumi.export("bastion_fip", bastion_fip.address)
