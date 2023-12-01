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

def count(self, list_to_count):
    return Counter(list_to_count)



    def visualize_dependencies(self, dependencies):
        dot = graphviz.Digraph(comment='cpp_dependencies',
                            node_attr={
                                    'fontname': 'Helvetica,Arial,sans-serif',
                                    'fontsize':'10',
                                    'shape':'box',
                                    'height':'0.25',
                                },
                            edge_attr=
                            {
                                    'fontname': 'Helvetica,Arial,sans-serif',
                                    'fontsize':'10',
                            },
                            graph_attr={"rankdir":"LR"})

        cnt = 0
        for file, dependent_files in dependencies.items():
            short_file = Path(file).name
            dot.node(short_file)
            for dependent_file in dependent_files:
                short_dependent_file = str(Path(dependent_file))
                dot.edge(short_file, short_dependent_file)

            cnt += 1
            if cnt > 1:
                break

        dot.render('cpp_dependencies', format='png', cleanup=True, directory="asd", outfile='dependencies.png')


if __name__ == "__main__":
    build_directory = "build/host_c66"

    ninja_build = NinjaBooster(build_directory)
    compile_rules = ninja_build.filter_rules(contains="_COMPILER")
    compile_targets = ninja_build.get_all_targets(compile_rules)

    for compile_target in compile_targets:
        d = ninja_build.get_in_tree_target_dependencies(compile_target)
        pass


