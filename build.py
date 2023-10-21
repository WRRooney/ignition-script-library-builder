# coding=utf-8
#
#  build.py
#  Ignition utility to convert between a standard python
#  project structure and an Ignition script library structure.
#
#  Author: Will Rooney
#
#  Last Modified: 10/20/2023
#  Last Modified By: Will Rooney
#

import argparse
import json
import os
import shutil


def generate_resource_data():
    return {
        "scope": "A",
        "version": 1,
        "restricted": False,
        "overridable": True,
        "files": [
            "code.py"
        ],
        "attributes": {
            "lastModification": {
                "actor": "external",
                "timestamp": "2023-01-01T00:00:00Z"
            },
            "hintScope": 2,
            "lastModificationSignature": "b0559c76c17737786bda6d382e91f682211c23721930003c538aeef6a42a577d"
        }
    }


def convert_import_statement_to_alias(statement, module):
    """
    Convert import statements to local variable aliases for the targeted module.

    Args:
        statement (str): The import statement.
        module (str): The root module that is being targeted.

    Returns:
        list[str]: List of modified import statements.
    """
    if statement.startswith('from {}'.format(module)):
        fq_module, funcs = statement.split(' import ')
        fq_module = fq_module[5:]  # strip 'from ' off the fully qualified module name
        funcs = funcs.split(',')
        return [
            '{0} = {1}.{0}'.format(func.strip(), fq_module)
            for func in funcs
        ]

    if statement.startswith('import {}'.format(module)):
        fq_module = statement.replace('import ', '')
        library_item = fq_module.rsplit('.', 1)[-1]
        return ['{} = {}'.format(library_item, fq_module)]

    return []


def convert_import_statements_to_aliases(code, source_modules):
    """
    Process the lines to find targeted import statements and create aliases in place.

    Args:
        code (str): The contents of the python code.
        source_modules (list[str]): List of root module names to target.
            *Should only be root modules meant to be converted to root Ignition script library modules and/or
             the ignition `system` API library.

    Returns:
        str: The modified code.
    """
    new_lines = []
    for line in code.split('\n'):

        # Comment out all ignition system library imports
        for module in source_modules:
            if line.startswith('from %s' % module) or line.startswith('import %s' % module):
                new_lines.append('# ' + line.strip())
                new_lines.extend(convert_import_statement_to_alias(line.strip(), module))
                break
        else:
            new_lines.append(line)
    return '\n'.join(new_lines)


def undo_aliased_import_statements(code, source_modules):
    """
    Process the lines to find targeted import statements and undo aliases put in place.
    * Requires original modifications to be intact or the pattern followed if changes are made from
      within the Ignition script library.

    Args:
        code (str): The contents of the python code.
        source_modules (list[str]): List of root module names to target.

    Returns:
        str: The modified code.
    """
    new_lines = []
    aliased_statements = []
    for line in code.split('\n'):
        if line.startswith('# '):
            uncommented = line.strip()[2:]
            matched = False
            for module in source_modules:
                if uncommented.startswith('from %s' % module) or uncommented.startswith('import %s' % module):
                    new_lines.append(uncommented)
                    aliased_statements.extend(convert_import_statement_to_alias(uncommented, module))
                    matched = True
                    break
            if not matched:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return '\n'.join(
        line
        for line in new_lines
        if line not in aliased_statements
    )


def reverse_build(project_folder, build_folder, source_modules, clean):
    """
    Traverse an Ignition script library and convert it to a standard python project structure.

    Args:
        project_folder (str): The destination python project folder.
        build_folder (str): The source Ignition script library folder.
        source_modules (list[str]): List of root module names to target.
        clean (bool): If true, ALL FOLDERS/FILES in the project folder will be deleted before reversing the build.
    """
    if clean:
        # Clear the contents of the project folder
        if os.path.exists(project_folder):
            shutil.rmtree(project_folder)

    def process_directory(directory, parent_folder=""):
        items = os.listdir(directory)

        if 'code.py' in items:
            source_path = os.path.join(directory, 'code.py')
            destination_path = os.path.join(project_folder, parent_folder + '.py')

            with open(source_path, 'r') as f:
                py_code = f.read()

            # Undo the python 3.x coding specification revision
            py_code = py_code.replace('# CODING=', '# coding=', 1)

            # Undo aliased statements
            py_code = undo_aliased_import_statements(py_code, source_modules)

            with open(destination_path, 'w') as py_file:
                py_file.write(py_code)
        else:
            folder_path = os.path.join(project_folder, parent_folder)
            init_file_path = os.path.join(folder_path, '__init__.py')
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
            with open(init_file_path, 'w') as _:
                pass
            for item in items:
                item_path = os.path.join(directory, item)
                if os.path.isdir(item_path):
                    rpath = os.path.join(parent_folder, item)
                    process_directory(item_path, rpath)

    process_directory(build_folder)


def build(project_folder, build_folder, source_modules, clean):
    """
    Traverse a python project and deploy it to a build folder using the
    Ignition script library structure.

    Args:
        project_folder (str): The source python project folder.
        build_folder (str): The destination Ignition script library folder.
        source_modules (list[str]): List of root module names to target.
            *Should only be root modules meant to be converted to root Ignition script library modules and/or
             the ignition `system` API library.
        clean (bool): If true, ALL FOLDERS/FILES in the build folder will be deleted before re-deploying build.
    """
    if clean:
        # Clear the contents of the build folder
        if os.path.exists(build_folder):
            shutil.rmtree(build_folder)

    def process_py_file(path, destination_folder):
        with open(path, 'r') as py_file:
            py_code = py_file.read()

        # Revise python 3.x coding specification such that
        # it doesn't cause issues in jython
        py_code = py_code.replace('# coding=', '# CODING=', 1)

        # Convert package level import statements to local variable aliases
        py_code = convert_import_statements_to_aliases(py_code, source_modules)

        # Create destination folder and save code.py
        name = os.path.basename(path)
        code_folder = os.path.join(destination_folder, os.path.splitext(name)[0])
        if not os.path.exists(code_folder):
            os.makedirs(code_folder)

        with open(os.path.join(code_folder, 'code.py'), 'w') as code_file:
            code_file.write(py_code)

        # Create resource.json
        with open(os.path.join(code_folder, 'resource.json'), 'w') as resource_file:
            resource_file.write(json.dumps(generate_resource_data(), indent=2))

    for root, dirs, files in os.walk(project_folder):
        for dir_name in dirs:
            # Exclude module __init__.py files
            if dir_name != '__pycache__':
                destination_dir = os.path.join(build_folder,
                                               os.path.relpath(os.path.join(root, dir_name), project_folder))
                if not os.path.exists(destination_dir):
                    os.makedirs(destination_dir)

        for file_name in files:
            if file_name.endswith('.py') and '__init__' not in file_name:
                py_file_path = os.path.join(root, file_name)
                destination_dir = os.path.join(build_folder, os.path.relpath(root, project_folder))
                process_py_file(py_file_path, destination_dir)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Build project to Ignition's script library.")

    parser.add_argument(
        "-s", "--source",
        default=os.path.join(os.getcwd(), 'src'),
        help="Source code folder path"
    )
    parser.add_argument(
        "-d", "--destination",
        default=os.path.join(os.getcwd(), 'ignition-data/projects/<ProjectName>/ignition/script-python'),
        help="Output build folder path"
    )
    parser.add_argument(
        "-c", "--clean",
        default=False,
        help="Delete all files and folders in the build folder before running, or the project folder if running a reverse build."
    )
    parser.add_argument(
        "-r", "--reverse", action="store_true",
        help="Reverse the build. WARNING will overwrite the source code project folder."
    )
    parser.add_argument(
        '-l', '--source_modules',
        nargs='+', default=['system'],
        help='Define all script modules being converted to allow import statements to be converted to aliases.'
    )
    args = parser.parse_args()

    source = os.path.abspath(args.source)
    destination = os.path.abspath(args.destination)

    if args.reverse:
        reverse_build(source, destination, args.source_modules, args.clean)
    else:
        build(source, destination, args.source_modules, args.clean)