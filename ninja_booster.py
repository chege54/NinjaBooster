import subprocess
import os
import re
import graphviz
from pathlib import Path
from collections import Counter
import pandas as pd

class NinjaBooster:
    NINJA_VERSION = 1.11

    def __init__(self, build_dir, root_folder=None) -> None:
        self.root_folder = root_folder and os.path.isdir(root_folder) or os.getcwd()
        self.build_dir = build_dir if os.path.isabs(build_dir) else os.path.normpath(f"{self.root_folder}/{build_dir}")
        self.rules = self._get_all_ninja_rules()
        self.targets_per_rule: dict = self._collect_targets_of_rules()
        self.file_dependencies_per_target: dict  = self._collect_file_dependencies_of_targets()
        self.inputs_per_target: dict  = self._collect_inputs_of_targets()

    '''
        Internal functions
        Helper member function to call ninja tooling
        Collecting all data, rules, targets, commands from ninja.build file.
    '''
    def _call_ninja_tool(self, toolname) -> list:
        re = subprocess.check_output(f"ninja -C {self.build_dir} -t {toolname}", shell=True, universal_newlines=True)
        return [r for r in re.splitlines() if r] # filter out "" strings

    def _get_all_ninja_rules(self) -> list:
        all_rules = self._call_ninja_tool('rules')
        return all_rules

    def _collect_targets_of_rules(self):
        targets_per_rule = dict()
        for rule in self.rules:
            targets = self._get_targets(rule)
            targets_per_rule.update({rule : targets})
        return targets_per_rule

    def _get_targets(self, rule_name:str) -> list:
        targets = self._call_ninja_tool(f"targets rule {rule_name}")
        return targets

    def _get_command(self, target:str) -> str:
        cmd = self._call_ninja_tool(f"commands {target}")
        return " ".join(cmd)

    def _get_target_dependencies(self, target:str) -> list:
        raw_deps = self._call_ninja_tool(f"deps {target}")
        if not target in raw_deps[0]:
            print(f"{raw_deps} is not for {target} - something went wrong!")

        all_deps = [os.path.normpath(raw_dep.strip()) for raw_dep in raw_deps[1:]]
        return all_deps

    def _collect_file_dependencies_of_targets(self):
        dependencies_of_target = dict()
        for _, targets in self.targets_per_rule.items():
            for target in targets:
                deps = self._get_target_dependencies(target)
                if deps:
                    dependencies_of_target.update({target : deps})
        return dependencies_of_target

    def _collect_file_inputs(self, target:str):
        inputs = self._call_ninja_tool(f"inputs {target}")
        input_files = []
        for i in inputs:
            if os.path.isfile(i):
                input_files.append(i)
            else:
                input_files.extend(self._collect_file_inputs(i))
        return input_files

    def _collect_inputs_of_targets(self):
        inputs_per_targets = dict()
        for _, targets in self.targets_per_rule.items():
            for target in targets:
                if target.endswith(".o"):
                    # Do it only if target is an object file - it causes huge runtime for install files
                    inputs = self._collect_file_inputs(target)
                    inputs_per_targets.update({target : inputs})

        return inputs_per_targets


    ''' API functions which should be called '''
    '''
        Filter rules from which contains the given substring
    '''
    def filter_rules(self, contains: str="_COMPILER") -> list:
        filtered_rules = filter(lambda x: contains in x , self.rules)
        return list(filtered_rules)

    '''
        Get all targets that uses the defined rule
    '''
    def get_targets(self, rule_name:str) -> list:
        targets = self.targets_per_rule.get(rule_name, [])
        return targets

    '''
        Cumulate all targets that uses the given list of rules
    '''
    def get_all_targets(self, rules:list) -> list:
        collected_targets = []
        for rule_name in rules:
            targets = self.get_targets(rule_name)
            collected_targets += targets

        return collected_targets

    '''
        Returns target dependencies - .cpp, .hpp, etc... are returned
    '''
    def get_target_dependencies(self, target_name:str) -> list:
        dependent_files = self.file_dependencies_per_target.get(target_name, [])
        return dependent_files

    '''
    '''
    def in_tree(self, file_path:str, root:str=None) -> bool:
        root_folder = root or self.root_folder
        dep_path = os.path.normpath(file_path.strip())
        return os.path.commonpath((root_folder, dep_path)) == root_folder

    '''
        Gen non-system and non-external dependencies
    '''
    def get_in_tree_target_dependencies(self, target:str) -> list:
        all_deps = self.get_target_dependencies(target)
        in_tree_deps =[dep for dep in all_deps if self.in_tree(dep)]

        return in_tree_deps

    '''
    '''
    def get_all_include_dirs(self, target:str) -> list:
        cmd = self._get_command(target)
        # TODO: expand @file if there is any
        include_dirs = re.findall(r"\s-I\s?([\w\/\.]+)", cmd)
        return include_dirs

    '''
    '''
    def get_in_tree_include_dirs(self, target:str) -> list:
        all_dirs = self.get_all_include_dirs(target)
        in_tree_dirs = [dir for dir in all_dirs if self.in_tree(dir)]
        return in_tree_dirs

def count(dictionary):
    all_values = []
    for _, vals in dictionary.items():
        all_values.extend(vals)
    all_values_set = set(all_values)

    return Counter(all_values), all_values_set

def to_dataframe(dictionary, index):
    pass

def get_compiled_target_deps(ninja_build_info: NinjaBooster, in_tree_only:bool=True) -> dict:
    target_deps = dict()
    compile_rules = ninja_build_info.filter_rules(contains="_COMPILER")
    compile_targets = ninja_build_info.get_all_targets(compile_rules)
    for compile_target in compile_targets:
        d = ninja_build_info.get_in_tree_target_dependencies(compile_target) if in_tree_only \
            else  ninja_build_info.get_target_dependencies(compile_target)
        target_deps.update({compile_target : d})

    return target_deps

def visualize(dict_to_visu, trim_str="", filtered_nodes:list = [], key_filename_only:bool = True, value_filename_only:bool = False):
    dot = graphviz.Digraph(comment='vizu',
        node_attr={
            'fontname': 'Helvetica,Arial,sans-serif',
            'fontsize':'10',
            'shape':'box',
            'height':'0.25',
        },
        edge_attr={
            'fontname': 'Helvetica,Arial,sans-serif',
            'fontsize':'10',
        },
        graph_attr={
            "rankdir":"LR"
        })

    def keep_it(node_name:str, postive_strings:list):
        keep_it = False or not postive_strings
        for p in postive_strings:
            # positive filter to keep only the wanted nodes
            keep_it = keep_it or (p in node_name)
        return keep_it

    for key, vals in dict_to_visu.items():
        node_name = re.sub(rf"^{trim_str}","", key)
        if not keep_it(node_name, filtered_nodes):
            continue

        if key_filename_only:
            node_name = os.path.basename(node_name)
        dot.node(node_name)
        for value in vals:
            value_node_name = re.sub(rf"^{trim_str}","", value)
            if value_filename_only:
                node_name = os.path.basename(node_name)
            dot.edge(node_name, value_node_name)

    dot.render(filename='graphviz.dot', format='png', cleanup=False, outfile='graphviz.png')


if __name__ == "__main__":
    # Arg parser:
    # TODO
    build_directory = "build/host_c66"

    # Create env.
    ninja_build_info = NinjaBooster(build_directory)
    target_dep_dict = get_compiled_target_deps(ninja_build_info, in_tree_only=True)

    # Statistics
    dependency_counts, dependency_set = count(target_dep_dict)
    print(f"TOP 5 dependencies are: {dependency_counts.most_common(5)}")

    # Visualize
    visualize(target_dep_dict, trim_str=ninja_build_info.root_folder)# filtered_nodes=[""]
    df = to_dataframe(target_dep_dict, dependency_set)
