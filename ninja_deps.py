import subprocess
import os

def get_all_ninja_rules(build_dir:str):
    all_rules = subprocess.check_output(f"ninja -C {build_dir} -t rules", shell=True, universal_newlines=True)
    return all_rules.splitlines()

def filter_rules(all_rules: list, contains: str="_COMPILER"):
    rules = filter(lambda x: contains in x , all_rules)
    return rules

def get_targets(build_dir:str, rules:list):
    targets = []
    for r in rules:
        re = subprocess.check_output(f"ninja -C {build_dir} -t targets rule {r}", shell=True, universal_newlines=True)
        targets += re.splitlines()

    return targets

def get_dependencies(build_dir:str, target:str):
    inputs = subprocess.check_output(f"ninja -C {build_dir} -t inputs {target}", shell=True, universal_newlines=True)
    deps = subprocess.check_output(f"ninja -C {build_dir} -t deps {target}", shell=True, universal_newlines=True)

    file_inputs = set(i for i in inputs.splitlines() if os.path.isfile(i))
    file_deps = set(d.strip() for d in deps.splitlines() if os.path.isfile(d.strip()))
    all_deps = set()
    if len(file_inputs) == 1:
        # compile target should have one input file #TODO: recursively check non file inputs
        all_deps = file_deps - file_inputs
    else:
        print(f"Warning input files '{file_inputs}' for '{target}'")

    return all_deps

def filter_in_tree_deps(root_directory:str, files:set()):
    return [f for f in files if root_directory in f]

def get_target_dep_files(root_directory, build_directory, compile_targets):
    re_dict = dict()

    for target in compile_targets:
        dep_files = get_dependencies(build_directory, target)
        in_tree_dep_files = filter_in_tree_deps(root_directory, dep_files)
        re_dict[target] = in_tree_dep_files

    return re_dict


if __name__ == "__main__":
    root_directory = "/home/noh2bp/mnt/ws"
    build_directory = f"{root_directory}/build/host_c66"

    # 1. get all rules from ninja.build
    all_rules = get_all_ninja_rules(build_directory)

    # 2. filter CXX_COMPILER_ rules
    compile_rules = filter_rules(all_rules)

    # 3. get CXX_COMPILER_ and phony rule targets
    compile_targets = get_targets(build_directory, compile_rules)

    # 4. get all dependencies from .ninja_deps for given targets
    target_dep_files_dict = get_target_dep_files(root_directory, build_directory, compile_targets)
    pass