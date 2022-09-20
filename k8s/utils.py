"""utils module for main"""
import os
import pulumi

def write_to_file(file: str, mode: str, content: str, filemode: int) -> None:
    """write hosts file with a different mode"""
    with open(file, mode, encoding="utf-8") as o_file:
        o_file.write(f"{content}\n")
    os.chmod(file, filemode)

def _write_to_yaml(file: str, mode: str, content: str, filemode: int) -> None:
    """write vars yaml file"""
    with open(file, mode, encoding="utf-8") as o_file:
        (name, ip_address) = content.split(sep=" ")
        o_file.write(f"  - {{'name': '{name}', 'ip': '{ip_address}'}}\n")
    os.chmod(file, filemode)

def create_hosts(ip_addresses: list):
    """create hosts file."""
    hosts_prepend = """127.0.0.1 localhost localhost.localdomain localhost4 localhost4.localdomain4
::1         localhost localhost.localdomain localhost6 localhost6.localdomain6
"""
    tmp_vars_prepend = f"""---
taco_tarball_url: '{pulumi.Config().get('taco_tarball_url')}'
cluster_name: '{pulumi.Config().get('cluster_name')}'
hosts_ini:"""
    write_to_file("hosts", "w", hosts_prepend, 0o644)
    write_to_file("tmp_vars", "w", tmp_vars_prepend, 0o644)
    i_no = 0
    for d_ip in ip_addresses:
        i_no += 1
        pulumi.Output.all(d_ip["ip"], d_ip["name"]).apply(
            lambda v: write_to_file("hosts", "a", f"{v[0]} {v[1]}", 0o644)
        )
        pulumi.Output.all(d_ip["name"], d_ip["ip"]).apply(
            lambda v: _write_to_yaml("tmp_vars", "a", f"{v[0]} {v[1]}", 0o644)
        )
        if i_no == len(ip_addresses):
            pulumi.Output.all(d_ip["name"], d_ip["fip"]).apply(
                lambda v: write_to_file(
                    "ansible_hosts",
                    "w",
                    f"{v[0]} ansible_host={v[1]} ansible_user=clex",
                    0o644,
                )
            )

    return True
