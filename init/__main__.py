"""A PBOS Initialization Pulumi Program"""
import os
import requests

import pulumi
import pulumi_openstack as openstack
import pulumi_command as command

config = pulumi.Config()

# create a selfservice network
o_selfservice = config.require_object("selfservice")
selfservice_net = openstack.networking.Network(
    "selfservice_net",
    name=f"o_selfservice['name']-net",
    admin_state_up=True,
)
# create a selfservice subnet
selfservice_subnet = openstack.networking.Subnet(
    "selfservice_subnet",
    name=f"o_selfservice['name']-subnet",
    cidr=o_selfservice['cidr'],
    ip_version=4,
    dns_nameservers=[dns_nameserver],
    network_id=selfservice_net.id,
)
# create a provider network
o_provider = config.require_object("provider")
provider_net = openstack.networking.Network(
    "provider_net",
    name=f"o_provider['name']-net",
    admin_state_up=True,
)
# create a provider subnet
provider_subnet = openstack.networking.Subnet(
    "provider_subnet",
    name=f"o_provider['name']-subnet",
    cidr=o_provider['cidr'],
    ip_version=4,
    dns_nameservers=[dns_nameserver],
    allocation_pools=[
        SubnetAllocationPool(
            start=o_provider['pool_start'],
            end=o_provider['pool_end'],
        )
    ],
    network_id=provider_net.id,
)
## create an image
#o_img = config.require_object("image")
#IMAGE_URL = f"{o_img['url']}"
#IMAGE_NAME = f"{o_img['name']}"
## get the latest cirros version
#response = requests.get(f"{IMAGE_URL}/version/released")
#image_version: str = response.content.rstrip().decode('utf-8')
#image_file: str = f"cirros-{image_version}-x86_64-disk.img"
#if not os.path.isfile(image_file):
#    download_url: str = f"{IMAGE_URL}/{image_version}/{image_file}"
#    response = requests.get(download_url)
#    with open(f"{image_file}", "wb") as f:
#        f.write(response.content)
#
#image = openstack.images.Image(
#    "image",
#    name=IMAGE_NAME,
#    container_format="bare",
#    disk_format="qcow2",
#    local_file_path=image_file,
#    properties={
#        "hw_disk_bus": "scsi",
#        "hw_scsi_model": "virtio-scsi",
#        "os_type": "linux",
#        "os_distro": "cirros",
#        "os_admin_user": "cirros",
#        "os_version": image_version,
#    }
#)
#
## create a flavor
#o_flavor = config.require_object("flavor")
#flavor = openstack.compute.Flavor(
#    "flavor",
#    name=f"{cluster_name}-flavor",
#    vcpus=o_flavor.get("vcpus"),
#    ram=o_flavor.get("ram")*1024,
#    disk=o_flavor.get("disk"),
#    is_public=True,
#)
#
## create a security group and rules
#sg = openstack.networking.SecGroup(
#    "sg",
#    name=f"{cluster_name}-sg",
#    description=f"Security Group for {cluster_name}",
#)
#sg_icmp = openstack.networking.SecGroupRule(
#    "sg_icmp",
#    direction="ingress",
#    ethertype="IPv4",
#    protocol="icmp",
#    remote_ip_prefix="0.0.0.0/0",
#    description="Allow incoming icmp",
#    security_group_id=sg.id,
#)
#sg_tcp_ssh = openstack.networking.SecGroupRule(
#    "sg_tcp_ssh",
#    direction="ingress",
#    ethertype="IPv4",
#    protocol="tcp",
#    port_range_min=22,
#    port_range_max=22,
#    remote_ip_prefix="0.0.0.0/0",
#    description="Allow incoming ssh service",
#    security_group_id=sg.id,
#)
#sg_tcp_registry = openstack.networking.SecGroupRule(
#    "sg_tcp_registry",
#    direction="ingress",
#    ethertype="IPv4",
#    protocol="tcp",
#    port_range_min=5000,
#    port_range_max=5000,
#    remote_ip_prefix="0.0.0.0/0",
#    description="Allow incoming registry service",
#    security_group_id=sg.id,
#)
#registry_fip = openstack.networking.FloatingIp(
#    "registry_fip",
#    pool=config.get("provider_network_name")
#)
## create an instance
#registry_instance = openstack.compute.Instance(
#    "registry",
#    name="registry",
#    flavor_id=flavor.id,
#    key_pair=keypair.id,
#    security_groups=[sg.name],
#    user_data=userdata_tmpl.stdout,
#    block_devices=[
#        openstack.compute.InstanceBlockDeviceArgs(
#            source_type="image",
#            destination_type="volume",
#            delete_on_termination=True,
#            volume_size=o_flavor.get("disk"),
#            uuid=image.id,
#        )
#    ],
#    networks=[
#        openstack.compute.InstanceNetworkArgs(
#            name=config.get("private_network_name")
#        ),
#    ],
#    opts=pulumi.ResourceOptions(
#        depends_on=[userdata_tmpl]
#    )
#)
#
#registry_fip_assoc = openstack.compute.FloatingIpAssociate(
#    "registry_fip_assoc",
#    fixed_ip=registry_instance.networks[0].fixed_ip_v4,
#    floating_ip=registry_fip.address,
#    instance_id=registry_instance.id,
#)
pulumi.export("image_id", image.id)
pulumi.export("image_name", image.name)
pulumi.export("image_size", image.size_bytes)
pulumi.export("image_status", image.status)
pulumi.export("registry_fip_address", registry_fip.address)
