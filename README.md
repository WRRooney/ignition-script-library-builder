# ignition-script-library-builder

A utility for converting a python project to an Ignition script library format and back.

### Recommended
https://pypi.org/project/ignition-api/

## Usage
```
python build.py <options>
```
### Command-Line Options

- `-s, --source` Source code folder path; the python project source code path. Defaults to: `./src`
- `-d, --destination` Output build folder path; the Ignition project script library. Defaults to: `ignition-data/projects/$PROJECT/ignition/script-python`
- `-r, --reverse` Convert an Ignition script library back into a standard project.
- `-c, --clean` WARNING: Will first delete all files and folders in the build folder, or the project folder if running a reverse build.
- `-l, --source_modules` Manually define script modules that will be targeted. Defaults to modules found in source folder.
- `-n, --tab_size` Number of spaces for that make up a tab.
- `-t, --no_char_to_tab` Disables conversion of source spaced indentation to tabs for Ignition script library.


### Example

Build a script library for an Ignition project 'MyProject':

```bash
python build.py --destination /usr/local/bin/ignition/data/projects/MyProject/ignition/script-python
```
