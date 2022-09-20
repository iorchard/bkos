"""A Fedora CoreOS VM Image Upload Pulumi Program"""
import os
import lzma
import requests

import pulumi
import pulumi_openstack as openstack

config = pulumi.Config()

# get fedora coreos image from url.
o_img = config.require_object("image")
IMAGE_URL = f"{o_img['url']}"
IMAGE_FILE = f"{o_img['file']}"
IMAGE_NAME = f"{o_img['name']}"
IMAGE_OS_VERSION = f"{o_img['properties']['os_version']}"
image_url = f"{IMAGE_URL}/{IMAGE_FILE}.xz"
if not os.path.isfile(IMAGE_FILE):
    if not os.path.isfile(f"{IMAGE_FILE}.xz"):
        response = requests.get(image_url)
        with open(f"{IMAGE_FILE}.xz", "wb") as f:
            f.write(response.content)

    with lzma.open(f"{IMAGE_FILE}.xz", "rb") as xz:
        with open(f"{IMAGE_FILE}", "wb") as f:
            f.write(xz.read())

image = openstack.images.Image(
    "image",
    name=IMAGE_NAME,
    container_format="bare",
    disk_format="qcow2",
    local_file_path=IMAGE_FILE,
    properties={
        "os_type": "linux",
        "os_distro": "fedora-coreos",
        "os_version": f"{IMAGE_OS_VERSION}",
        "hw_disk_bus": "scsi",
        "hw_scsi_model": "virtio-scsi"
    }
)

pulumi.export("image id", image.id)
pulumi.export("image name", image.name)
pulumi.export("image size", image.size_bytes)
pulumi.export("image status", image.status)
