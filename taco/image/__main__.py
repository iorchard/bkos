"""A TACO2 VM Image Upload Pulumi Program"""
import os
import tarfile
import requests

import pulumi
import pulumi_openstack as openstack

# get centos7 cloud image from url.
IMAGE_FILE = "CentOS-7-x86_64-GenericCloud-2003.raw"
IMAGE_NAME = "centos7"
image_url = f"https://cloud.centos.org/centos/7/images/{IMAGE_FILE}.tar.gz"
if not os.path.isfile(IMAGE_FILE):
    if not os.path.isfile(f"{IMAGE_FILE}.tar.gz"):
        response = requests.get(image_url)
        with open(f"{IMAGE_FILE}.tar.gz", "wb") as f:
            f.write(response.content)
    with tarfile.open(f"{IMAGE_FILE}.tar.gz", "r:gz") as t:
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(t)

image = openstack.images.Image(
    "image",
    name=IMAGE_NAME,
    container_format="bare",
    disk_format="raw",
    local_file_path=IMAGE_FILE,
    properties={
        "os_type": "linux",
        "os_distro": "centos",
        "os_version": "7-2003",
        "hw_disk_bus": "scsi",
        "hw_scsi_model": "virtio-scsi"
    }
)

pulumi.export("image id", image.id)
pulumi.export("image name", image.name)
pulumi.export("image size", image.size_bytes)
pulumi.export("image status", image.status)
