import subprocess
import os
import re
import graphviz
from pathlib import Path
from collections import Counter
import pandas as pd

class NinjaBooster:
    NINJA_VERSION = 1.11

    def __init__(self, build_dir, root_folder=None, build_all=True) -> None:
        self.root_folder = root_folder and os.path.isdir(root_folder) or os.getcwd()
        self.build_dir = build_dir if os.path.isabs(build_dir) else os.path.normpath(f"{self.root_folder}/{build_dir}")
        self.rules = self._get_all_ninja_rules()
        self.targets_per_rule: dict = self._collect_targets_of_rules()
        if(build_all):
            # os.isfile() check on compile and link outputs can work only after a build
            # ninja collects deps from compiler
            self._call_ninja_build()

        self.file_dependencies_per_target: dict  = self._collect_file_dependencies_of_targets()
        self.target_inputs_per_file_target: dict  = self._collect_inputs_of_file_targets()

    '''
        Internal functions
        Helper member function to call ninja tooling
        Collecting all data, rules, targets, commands from ninja.build file.
    '''
    def _call_ninja_tool(self, toolname) -> list:
        re = subprocess.check_output(f"ninja -C {self.build_dir} -t {toolname}", shell=True, universal_newlines=True)
        return [r for r in re.splitlines() if r] # filter out "" strings

    def _call_ninja_build(self, target='all') -> list:
        print(subprocess.check_output(f"ninja -C {self.build_dir} -j {os.cpu_count()} {target}", shell=True, universal_newlines=True))

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
        all_deps_set = set(all_deps)
        if len(all_deps) != len(all_deps_set):
            print(f"WARNING: {target} has {len(all_deps_set)} unique dependencies - Ninja collected: {len(all_deps)}. Duplicates are removed!")

        return list(all_deps_set)

    def _collect_file_dependencies_of_targets(self):
        dependencies_of_target = dict()
        for _, targets in self.targets_per_rule.items():
            for target in targets:
                deps = self._get_target_dependencies(target)
                if deps:
                    dependencies_of_target.update({target : deps})
        return dependencies_of_target

    ''' Method recursively collects until all file inputs are collected '''
    def _collect_file_inputs(self, target:str):
        inputs = self._call_ninja_tool(f"inputs {target}")
        input_files = []
        for i in inputs:
            if os.path.isfile(i):
                input_files.append(i)
            else:
                input_files.extend(self._collect_file_inputs(i))
        return input_files

    ''' TODO '''
    def _collect_file_inputs_of_targets(self):
        inputs_per_targets = dict()
        for _, targets in self.targets_per_rule.items():
            for target in targets:
                if target.endswith(".o") or target.endswith(".a"):
                    # Do it only if target is an object file - it causes huge runtime for install files
                    inputs = self._collect_file_inputs(target)
                    inputs_per_targets.update({target : inputs})

        return inputs_per_targets

    '''
    Method collects all file inputs of compile or link rule targets
     TODO: do not rely on rule name, just the output - it can be
     unstable on non CMAKE generated ninja.build/ninja.rules
    '''
    def _collect_inputs_of_file_targets(self):
        final_targets = dict()
        compile_link_targets = (targets for rule, targets in self.targets_per_rule.items()
                                if re.search(r'COMPILE|LINK', rule, re.IGNORECASE))
        # keep built(existing) and in build directory targets only
        file_targets = [target for targets in compile_link_targets
                        for target in targets if os.path.isfile(os.path.join(self.build_dir,target))
                        and not os.path.isabs(target)]
        # filter those targets that depends on another compile or link_targets (intermediate targets)
        for target in file_targets:
            immediate_inputs = [inp for inp in self._call_ninja_tool(f"inputs {target}")
                           if inp in file_targets]
            if immediate_inputs:
                final_targets.update({target:immediate_inputs})
        return final_targets


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

    '''
    '''
    def get_final_target_input_dependencies(self) -> dict:
        final_target_deps = dict()
        for final_target, intermediates in self.target_inputs_per_file_target.items():
            all_deps = []
            for i in intermediates:
                dependencies = self.file_dependencies_per_target.get(i, None)
                if dependencies:
                    all_deps.extend(dependencies)
            final_target_deps.update({final_target:set(all_deps)})
        return final_target_deps

    def get_in_tree_final_target_input_dependencies(self) -> dict:
        in_tree_final_target_deps = dict()
        for k, all_deps in self.get_final_target_input_dependencies().items():
            in_tree_deps =[dep for dep in all_deps if self.in_tree(dep)]
            in_tree_final_target_deps.update({k:in_tree_deps})
        return in_tree_final_target_deps

    def get_dependencies_folder(self, target_dependency_dict) -> dict:
        folder_deps = dict()
        for k, all_deps in target_dependency_dict.items():
            folders =(os.path.dirname(dep) for dep in all_deps if self.in_tree(dep))
            folder_deps.update({k: set(folders)})
        return folder_deps

def count(dictionary):
    all_values = []
    for _, vals in dictionary.items():
        all_values.extend(vals)
    all_values_set = set(all_values)

    return Counter(all_values), all_values_set

def to_dataframe(dictionary):
    df = pd.DataFrame()
    for key, values in dictionary.items():
        short_key = os.path.basename(key)
        data = ["X"] * len(values) # values are 'X', index = values, key is the col name
        df = df.join(pd.Series(data=data, index=values, name=short_key), how='outer')
    return df

def get_compiled_target_deps(ninja_build_info: NinjaBooster, in_tree_only:bool=True) -> dict:
    target_deps = dict()
    compile_rules = ninja_build_info.filter_rules(contains="_COMPILER")
    compile_targets = ninja_build_info.get_all_targets(compile_rules)
    for compile_target in compile_targets:
        d = ninja_build_info.get_in_tree_target_dependencies(compile_target) if in_tree_only \
            else  ninja_build_info.get_target_dependencies(compile_target)
        target_deps.update({compile_target : d})

    return target_deps

def visualize(dict_to_visu, filename="graphviz", trim_str="", filtered_nodes:list = [], key_filename_only:bool = True, value_filename_only:bool = False):
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

    dot.render(filename=f'{filename}.dot', format='png', cleanup=False, outfile=f'{filename}.png')

if __name__ == "__main__":
    # Arg parser:
    # TODO
    build_directory = "build/host_c66"

    # Create env.
    ninja_build_info = NinjaBooster(build_directory)
    target_dep_dict = get_compiled_target_deps(ninja_build_info, in_tree_only=True)
    target_folder_dependencies = ninja_build_info.get_dependencies_folder(target_dep_dict)

    in_tree_final_target_dependencies = ninja_build_info.get_in_tree_final_target_input_dependencies()
    in_tree_final_target_folder_dependencies = ninja_build_info.get_dependencies_folder(in_tree_final_target_dependencies)

    # Statistics
    dependency_counts, dependency_set = count(target_dep_dict)
    print("TOP 5 dependencies are:", *dependency_counts.most_common(5), sep="\n")

    # Visualize
    visualize(target_dep_dict, filename="object_deps" ,trim_str=ninja_build_info.root_folder)# filtered_nodes=[""]
    visualize(target_folder_dependencies, filename="object_deps_folder_deps")# filtered_nodes=[""]

    visualize(in_tree_final_target_dependencies, filename="final_target_deps", trim_str=ninja_build_info.root_folder)# filtered_nodes=[""]
    visualize(in_tree_final_target_folder_dependencies, filename="final_target_folder_deps", trim_str=ninja_build_info.root_folder)# filtered_nodes=[""]

    # dataframe
    df = to_dataframe(in_tree_final_target_dependencies)
    df.to_csv("dependency_matrix.csv")
    df.to_excel("dependency_matrix.xlsx")
