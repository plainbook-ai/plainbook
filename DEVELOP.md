# Plainbook Development

Contributions are welcome! If you want to contribute to the Plainbook project, please read the following guidelines.

## Coordinate your contribution

It is recommended to coordinate the changes with the maintainers ahead of time, by writing to the [Plainbook email list](https://groups.google.com/g/plainbook).  This ensures, for example, that two contributors do not work on the same feature at the same time, and that features do not conflict with planned changes. 

## Branching and pull requests

The main branch is `main`, and `develop` is the main development branch. 
For the time being, let Luca do the merges into the `develop` and `main` branches, and the pypi releases. 

When you work on something, branch from the `develop` branch, and submit a pull request to the `develop` branch.  
If you have access to the main repository, you can create your feature branch directly on the main repository, named something like `yourname-feature`.  Otherwise, you can fork the repository, create your feature branch on your fork, and submit a pull request to the `develop` branch of the main repository.  Clean up your feature branches from time to time. 

## Code style

Please follow the [PEP 8](https://peps.python.org/pep-0008/) style guide for Python code.  In particular, please use 4-space indentation, and include docstrings for all functions and classes.  Look also at the way the code is written now in the repository, and try to follow the same style.
