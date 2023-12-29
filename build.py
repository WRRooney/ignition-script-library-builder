# coding=utf-8
#
#  build.py
#  Ignition utility to convert between a standard python
#  project structure and an Ignition script library structure.
#
#  Author: Will Rooney
#
#  Last Modified: 12/29/2023
#  Last Modified By: Will Rooney
#

import argparse
import ast
import json
import os
import re
import shutil
import traceback
from collections import namedtuple

TAB_INDENT = 4


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


def get_imports(code):
    """ 
    https://stackoverflow.com/a/9049549
    
    Args:
        code (str): Extract import statement data. 

    Returns:
        namedtuple: ("Import", ["module", "name", "alias"])
    """
    Import = namedtuple("Import", ["module", "name", "alias"])
    root = ast.parse(code)
    for node in ast.iter_child_nodes(root):
        if isinstance(node, ast.Import):
            module = []
        elif isinstance(node, ast.ImportFrom):
            module = node.module.split('.')
        else:
            continue

        for n in node.names:
            yield Import(module, n.name.split('.'), n.asname)


def is_import_statement(line, target_modules):
    """
    Check if the statement is an import statement for the targeted module.

    Args:
        line (str): The line to check.
        target_modules (list[str]): List of root module names to target.

    Returns:
        bool: True if the statement is an import statement for the targeted module.
    """
    for target_module in target_modules:
        if line.startswith('from %s' % target_module) or line.startswith('import %s' % target_module):
            return True
    return False


def import_statement_to_aliases(statement, target_module):
    """
    Convert import statements to local variable aliases for the targeted module.

    Args:
        statement (str): The import statement.
        target_module (str): The root module(s) that are being targeted.

    Returns:
        list[str]: List of modified import statements.
    """
    alias_statements = []
    for imp in get_imports(statement):
        module = [x for x in imp.module] + imp.name
        if len(module) > 1 and module[0] == target_module:
            fq_module = '.'.join(module)
            name = module[-1] if imp.alias is None else imp.alias
            alias_statements.append('{} = {}'.format(name, fq_module))
    return alias_statements


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
        match = False
        if line.startswith('import system.'):
            new_lines.append('# ' + line.strip())
            match = True
        else:
            for module in source_modules:
                if line.startswith('from %s' % module) or line.startswith('import %s' % module):
                    new_lines.append('# ' + line.strip())
                    new_lines.extend(import_statement_to_aliases(line.strip(), module))
                    match = True
                    break
        if not match:
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
            if uncommented.startswith('import system.'):
                new_lines.append(uncommented)
                matched = True
            else:
                for module in source_modules:
                    if uncommented.startswith('from %s' % module) or uncommented.startswith('import %s' % module):
                        new_lines.append(uncommented)
                        aliased_statements.extend(import_statement_to_aliases(uncommented, module))
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


def split_statement_by_quoted_strings(statement):
    quote_chars = "'\""
    if not any(x in statement for x in quote_chars):
        return [statement]

    in_escape = False
    quoted_indexes = []  # (start, end)
    start = None
    for i, c in enumerate(statement):
        if start is not None and not in_escape and c == '\\':
            in_escape = True
            continue

        if start is not None and not in_escape and c in quote_chars:
            quoted_indexes.append((start, i))
            start = None
            continue

        if start is not None and in_escape and c in quote_chars:
            in_escape = False
            continue

        if start is None and c in quote_chars:
            start = i
            continue
    # Split the statement into parts that are quoted and not quoted
    parts = []
    last_end = 0
    for start, end in quoted_indexes:
        parts.append(statement[last_end:start])
        parts.append(statement[start:end + 1])
        last_end = end + 1
    parts.append(statement[last_end:])
    return parts if len(parts) else [statement]


def replace_reference(code, find, replace):
    """
    Replace all instances of a reference in the code. Must match entire word/reference.

    Args:
        code (str): The contents of the python code.
        find (str): The word to find.
        replace (str): The word to replace with.

    Returns:
        str: The modified code.
    """
    pattern = re.compile(r'\b' + re.escape(find) + r'\b')

    modified_lines = []
    multiline_quote = False
    quote_chars = "'\""
    for line in code.split('\n'):

        # Check if line is part of a multiline string
        if multiline_quote:
            parts = line.split('"""')
            # First part of line is part of multiline string
            # Replace the pattern on odd indexes of the parts list
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    # Split the part into parts that are quoted and not quoted
                    sub_parts = split_statement_by_quoted_strings(part)
                    # Replace the pattern on even indexes of the sub_parts list
                    for j, sub_part in enumerate(sub_parts):
                        if j % 2 == 0:
                            sub_parts[j] = pattern.sub(replace, sub_part)
                    parts[i] = ''.join(sub_parts)

            # If the last part of the line is part of multiline string
            # then the line is still part of multiline string
            if len(parts) % 2 != 1:
                multiline_quote = False

            modified_lines.append('"""'.join(parts))
            continue

        elif not line.strip().startswith('#') and '"""' in line:
            parts = line.split('"""')
            # First part of line is not part of multiline string
            # Replace the pattern on even indexes of the parts list
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    # Split the part into parts that are quoted and not quoted
                    sub_parts = split_statement_by_quoted_strings(part)
                    # Replace the pattern on even indexes of the sub_parts list
                    for j, sub_part in enumerate(sub_parts):
                        if j % 2 == 0:
                            sub_parts[j] = pattern.sub(replace, sub_part)
                    parts[i] = ''.join(sub_parts)
            # If the last part of the line is not part of multiline string
            # then the line is not part of multiline string
            if len(parts) % 2 != 1:
                multiline_quote = True

            modified_lines.append('"""'.join(parts))
            continue

        # Ignore comments
        if line.strip().startswith('#'):
            modified_lines.append(line)
            continue

        # Split the line into parts that are quoted and not quoted
        parts = split_statement_by_quoted_strings(line)
        # Even indexes are not quoted, odd indexes are quoted
        # Replace the pattern on even indexes of the parts list
        for i, part in enumerate(parts):
            if i % 2 == 0:
                parts[i] = pattern.sub(replace, part)
        modified_lines.append(''.join(parts))

    return '\n'.join(modified_lines)


def replace_import_statements_with_direct_references(code, source_modules):
    """
    Process the lines to find targeted import statements and adjust all usage to use direct references instead.

    Args:
        code (str): The contents of the python code.
        source_modules (list[str]): List of root module names to target.
            *Should only be root modules meant to be converted to root Ignition script library modules and/or
             the ignition `system` API library.

    Returns:
        str: The modified code.
    """
    new_lines = []
    replacements = {}
    multi_line_import = None
    for line in code.split('\n'):

        # Comment out all ignition system library imports
        match = False
        if line.startswith('import system.'):
            new_lines.append('# ' + line.strip())
            match = True
        else:
            if multi_line_import is not None:
                # Flatten import statement to single line; irreversible
                if line.strip().endswith('\\'):
                    multi_line_import += line.strip()[:-1]
                    continue
                else:
                    line = multi_line_import + line.strip()
                    multi_line_import = None

            if multi_line_import is None and is_import_statement(line.strip(), source_modules):
                match = True

                if line.strip().endswith('\\'):
                    line = line.strip()[:-1]
                    multi_line_import = line
                    continue

                new_lines.append('# ' + line.strip())

                # Keep track of all imports that need to be used to replace objects with direct references.
                for imp in get_imports(line.strip()):
                    module = [x for x in imp.module] + imp.name
                    if len(module) > 1 and module[0] in source_modules:
                        fq_module = '.'.join(module)
                        name = module[-1] if imp.alias is None else imp.alias
                        replacements[name] = fq_module

        if not match:
            new_lines.append(line)

    new_lines = '\n'.join(new_lines)

    # Replace all references to the aliased imports with direct references
    for name, fq_module in replacements.items():
        new_lines = replace_reference(new_lines, name, fq_module)

    return new_lines


def undo_replace_import_statements_with_direct_references(code, source_modules):
    """
    Process the lines to find targeted import statements and undo direct references put in place.
    * Requires original modifications to be intact or the pattern followed if changes are made from
      within the Ignition script library.

    Args:
        code (str): The contents of the python code.
        source_modules (list[str]): List of root module names to target.

    Returns:
        str: The modified code.
    """
    new_lines = []
    replacements = {}
    for line in code.split('\n'):
        if line.startswith('# '):
            uncommented = line.strip()[2:]
            match = False
            if uncommented.startswith('import system.'):
                new_lines.append(uncommented)
                match = True
            else:
                for target_module in source_modules:
                    if uncommented.startswith('from %s' % target_module) or uncommented.startswith('import %s' % target_module):
                        new_lines.append(uncommented)
                        match = True

                        # Keep track of all imports that need to be used to replace objects with direct references.
                        for imp in get_imports(line.strip()):
                            module = [x for x in imp.module] + imp.name
                            if len(module) > 1 and module[0] == target_module:
                                fq_module = '.'.join(module)
                                name = module[-1] if imp.alias is None else imp.alias
                                replacements[name] = fq_module

                        break

            if not match:
                new_lines.append(line)
        else:
            new_lines.append(line)

    new_lines = '\n'.join(new_lines)

    # Replace all direct references with the aliased import names
    for name, fq_module in replacements.items():
        new_lines = replace_reference(new_lines, fq_module, name)

    return new_lines


def reverse_build(project_folder, build_folder, source_modules, clean, char_to_tab, tab_size):
    """
    Traverse an Ignition script library and convert it to a standard python project structure.

    Args:
        project_folder (str): The destination python project folder.
        build_folder (str): The source Ignition script library folder.
        source_modules (list[str]): List of root module names to target.
        clean (bool): If true, ALL FOLDERS/FILES in the project folder will be deleted before reversing the build.
        char_to_tab (booL): If true, all tabs will be converted back to spaces.
        tab_size (int): The number of spaces that make up a tab.
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
            # py_code = undo_aliased_import_statements(py_code, source_modules)

            # Undo direct references
            try:
                py_code = undo_replace_import_statements_with_direct_references(py_code, source_modules)
            except SyntaxError:
                raise SyntaxError('{}: {}'.format(traceback.format_exc(), source_path))

            if char_to_tab:
                py_code = py_code.replace('\t', ' ' * tab_size)

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


def build(project_folder, build_folder, source_modules, clean, char_to_tab, tab_size):
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
        char_to_tab (booL): If true, all groups of `tab_size` spaces will be converted to tabs.
        tab_size (int): The number of spaces that make up a tab.
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
        # py_code = convert_import_statements_to_aliases(py_code, source_modules)

        # Convert import statements to direct references
        try:
            py_code = replace_import_statements_with_direct_references(py_code, source_modules)
        except SyntaxError:
            raise SyntaxError('{}: {}'.format(traceback.format_exc(), path))

        if char_to_tab:
            py_code = py_code.replace(' ' * tab_size, '\t')

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

    default_source = os.path.join(os.getcwd(), 'src')
    default_destination = os.path.join(os.getcwd(), 'ignition-data/projects/$PROJECT/ignition/script-python')
    default_modules = [
        item for item in os.listdir(default_source)
        if os.path.isdir(os.path.join(default_source, item))
    ]

    parser = argparse.ArgumentParser(description="Build project to Ignition's script library.")

    parser.add_argument(
        "-s", "--source",
        default=default_source,
        help="Source code folder path; the python project source code path."
    )
    parser.add_argument(
        "-d", "--destination",
        default=default_destination,
        help="Output build folder path; the Ignition script library path."
    )
    parser.add_argument(
        "-c", "--clean",
        action="store_true",
        help="First delete all files and folders in the build folder, or the project folder if a reverse build."
    )
    parser.add_argument(
        "-r", "--reverse", action="store_true",
        help="Reverse the build. WARNING will overwrite the source code project folder."
    )
    parser.add_argument(
        '-l', '--source_modules',
        nargs='+', default=default_modules,
        help='Define script modules that will be targeted to convert import statements to local aliases. Defaults to '
             'modules found in project.'
    )
    parser.add_argument(
        '-n', '--tab_size',
        default=4,
        help='Number of spaces for that make up a tab.'
    )
    # Add argument to disable the conversion of tabs to spaces. 
    parser.add_argument(
        '-t', '--no_char_to_tab',
        action='store_true',
        help='Disable the conversion of tabs to spaces.'
    )
   
    args = parser.parse_args()

    source = os.path.abspath(args.source)
    destination = os.path.abspath(args.destination)

    if args.reverse:
        reverse_build(source, destination, args.source_modules, args.clean, not args.no_char_to_tab, args.tab_size)
    else:
        build(source, destination, args.source_modules, args.clean, not args.no_char_to_tab, args.tab_size)
