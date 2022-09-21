"""A Fedora CoreOS VM Image Upload Pulumi Program"""
import os
import lzma
import requests

import pulumi
import pulumi_openstack as openstack

config = pulumi.Config()

# get fedora coreos image from url.
o_img = config.require_object("fcos_image")
IMAGE_URL = f"{o_img['url']}"
IMAGE_FILE = f"{o_img['file']}"
IMAGE_NAME = f"{o_img['name']}"
IMAGE_OS_VERSION = f"{o_img['os_version']}"
image_url = f"{IMAGE_URL}/{IMAGE_FILE}.xz"
if not os.path.isfile(IMAGE_FILE):
    if not os.path.isfile(f"{IMAGE_FILE}.xz"):
        response = requests.get(image_url)
        with open(f"{IMAGE_FILE}.xz", "wb") as f:
            f.write(response.content)

    with lzma.open(f"{IMAGE_FILE}.xz", "rb") as xz:
        with open(f"{IMAGE_FILE}", "wb") as f:
            f.write(xz.read())

fcos_image = openstack.images.Image(
    "fcos_image",
    name=IMAGE_NAME,
    container_format="bare",
    disk_format="qcow2",
    local_file_path=IMAGE_FILE,
    properties={
        "hw_disk_bus": "scsi",
        "hw_scsi_model": "virtio-scsi",
        "os_type": "linux",
        "os_distro": "fedora-coreos",
        "os_admin_user": "core",
        "os_version": f"{IMAGE_OS_VERSION}",
    }
)
# get debian image from url.
o_img = config.require_object("debian_image")
IMAGE_URL = f"{o_img['url']}"
IMAGE_FILE = f"{o_img['file']}"
IMAGE_NAME = f"{o_img['name']}"
IMAGE_OS_VERSION = f"{o_img['os_version']}"
image_url = f"{IMAGE_URL}/{IMAGE_FILE}"
if not os.path.isfile(IMAGE_FILE):
    response = requests.get(image_url)
    with open(f"{IMAGE_FILE}", "wb") as f:
        f.write(response.content)

debian_image = openstack.images.Image(
    "debian_image",
    name=IMAGE_NAME,
    container_format="bare",
    disk_format="qcow2",
    local_file_path=IMAGE_FILE,
    properties={
        "hw_disk_bus": "scsi",
        "hw_scsi_model": "virtio-scsi",
        "os_type": "linux",
        "os_distro": "debian",
        "os_admin_user": "debian",
        "os_version": f"{IMAGE_OS_VERSION}",
    }
)

pulumi.export("fcos_image_id", fcos_image.id)
pulumi.export("fcos_image_name", fcos_image.name)
pulumi.export("fcos_image_size", fcos_image.size_bytes)
pulumi.export("fcos_image_status", fcos_image.status)
pulumi.export("debian_image_id", debian_image.id)
pulumi.export("debian_image_name", debian_image.name)
pulumi.export("debian_image_size", debian_image.size_bytes)
pulumi.export("debian_image_status", debian_image.status)
