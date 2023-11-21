# ignition-script-library-builder

A utility for converting a standard Python project structure into an Ignition script library structure and back.

### Recommended python IDE modules
https://pypi.org/project/ignition-api/

## Usage
```
python build.py <options>
```
### Command-Line Options

- `-s, --source` Source code folder path; the python project source code path.
- `-d, --destination` Output build folder path; the Ignition script library path.
- `-r, --reverse` Convert an Ignition script library back into a python project.
- `-c, --clean` Before running the conversion delete all files and folders in the build folder, or the project folder if running a reverse build.
- `-l, --source_modules` Define script modules that will be targeted to convert import statements to local aliases. Defaults to modules found in project.
- `-t, --char_to_tab` Enable conversion of source spaced indentation to tabs for Ignition script library.
- `-n, --tab_size` Number of spaces for that make up a tab. 

### Example

Convert a Python project to a Ignition script library:

```bash
python build.py --source script-library --destination <ignition-dir>/data/projects/<MyProject>/ignition/script-python --clean True --source_modules <modules...>
```
 - Replace `<MyProject>` and `<ignition-dir>` with your specific project and Ignition directory paths.
 - Replace `<modules...>` with the script library packages you wish to target and all import statements will be converted to local aliased objects.
   - For example: `--source_modules system MyModule1 MyModule2`
