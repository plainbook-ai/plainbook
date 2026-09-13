# <img src="https://github.com/plainbook-ai/plainbook/raw/main/plainbook/images/Plainbook_logo.png" height="30"> Plainbook: Natural Language Notebooks

A Plainbook is a computational notebook, written in natural language rather than code. 

Normally you would generate a notebook with AI and then keep the code, discarding the natural language that produced it. 
Plainbook keeps the language instead: the code is generated and executed automatically, and can be validated and tested through natural language and data inspection — no coding knowledge required.
This lets you share your data analysis and science with a much wider audience, including people who don't know how to code.

Plainbooks resemble [Jupyter notebooks](https://jupyter.org/), in that they combine instructions and results in a single shareable document. 
They differ in these ways:

* **Linear semantics.** Cells execute strictly in order — the same order in which a human reads the natural-language description of the computation.
* **Dependency tracking.** Code analysis determines what a change actually affects, so only a minimal portion of the Plainbook is regenerated or re-executed.
* **Test cells.** Plainbook lets you test that individual cells implement their natural language descriptions via natural-language tests and data inspection. 

Linear semantics and dependency tracking are inspired by [Marimo](https://marimo.io/). 
The ability to test cells hinges on natural language and on the special [snapshot-kernel](https://plainbook-ai/snapshot-kernel/) underlying Plainbook. 

The goal of the project is to replicate in natural language what made Jupyter so successful: sharing code and results together, so that any recipient can validate and modify what they receive. 
Recipients can check that the generated code implements the natural-language tasks, and can edit the Plainbook, regenerate the code, and rerun it — just as in Jupyter or Marimo.

You can read more about the design phylosophy of Plainbook, and its code testing approach, in the paper  [Plainbook: Data Science, in Plain Language](https://arxiv.org/abs/2607.05717). 

### Try Plainbook Now

**Quick Start Videos:**
* [30-second demo](https://youtu.be/0t4ND8wPoYA)
* [5-minute introduction](https://youtu.be/Mkv5cl5rA7s)

**Run on GitHub Codespaces (no installation needed):**
1. Click **Code** → **Codespaces** in the GitHub interface
2. Wait ~3 minutes for the environment to set up
3. Click **Open in Browser** for port 8080
4. A trial Claude API key is provided; you can add your own in Settings

**Example Notebooks:**
* [Soccer World Cup Analysis](https://github.com/plainbook-ai/plainbook/raw/main/examples/Soccer_w_Tests.plnb) — demonstrates action cells, tests, and AI validation

## Installation and use

You can install Plainbook with pip: 

```bash
pip install plainbook
```

To open a plainbook (which will be created if it does not exist): 

```bash
plainbook notebook.plnb
```

You can use any file name you like, with any extension you like. 

**AI API Keys.** You need a Gemini, Claude, or OpenAI API key to use Plainbook. Click on the Settings button (the gear on the top right) to see instructions on how to set them. Usage costs are typically low for regular notebook work.

### Key Features

- **Natural language notebooks:** Describe what you want in plain English; AI generates and validates the code. 
- **Multiple AI providers:** Use Gemini, Claude, or OpenAI models—cross-check implementations for robustness.
- **Built-in testing:** Write test cells to verify notebook behavior automatically.
- **Shareable & reproducible:** Share notebooks with others who can modify, regenerate, and rerun your work.

### Resources

* [GitHub Repository](https://github.com/plainbook-ai/plainbook).
* [Pypi package](https://pypi.org/project/plainbook/).
* [Development mailing list](https://groups.google.com/g/plainbook).

## Plainbook Structure

Plainbooks consist of three types of cells: 

* **Action cells**, where the user describes in natural language the action to be performed (e.g., "Load the dataset from file data.csv and display the first 10 rows").  The system converts the description to code, executes it, and displays the results below the cell.

* **Comment cells**, where the user can add comments, section headers, and so forth, using markdown syntax. 

* **Test cells**, where the user can write properties that should hold at certain points of the notebook to check that everything is working as expected.

Differently from standard Jupyter notebooks, Plainbooks cells are guaranteed to be executed in order, from first to last, matching the order in which humans read the cells. Plainbooks relies on a [checkpointing kernel](https://github.com/plainbook-ai/snapshot-kernel) to remember the execution state after each cell, so that it can re-run a cell without having to start from the beginning.

**AI Providers**
Plainbook is designed to work with multiple AI providers, and users can choose which provider to use for code generation and checking.  The system is designed to allow users to easily switch between providers, so that users can cross-check that the implementation obtained from one provider is considered valid by another provider.  This avoids over-reliance on a single class of AI models. 
Currently, Plainbook supports Gemini, Claude, and OpenAI models.  You will need an API key for at least one such provider to use Plainbook.


## Papers

* L. de Alfaro, M. Aubert, R. Jhala, E. Pastor, E. Baralis. [_Plainbook: Data Science, in Plain Language_](https://arxiv.org/abs/2607.05717), July 2026.

## Citing Plainbook

To cite **the software**, use the Zenodo record — it has its own author list,
which is not the same as the paper's:

> L. de Alfaro, M. Aubert, R. Jhala, D. Soni, U. Ejiogu, E. Pastor, E. Baralis.
> _Plainbook: Natural Language Notebooks_ (software). BSD 3-Clause.
> https://doi.org/10.5281/zenodo.XXXXXXX

```bibtex
@software{plainbook,
  title     = {Plainbook: Natural Language Notebooks},
  author    = {de Alfaro, Luca and Aubert, Mathis and Jhala, Ranjit and
               Soni, Dhyan and Ejiogu, Uchechi and Pastor, Eliana and
               Baralis, Elena},
  year      = {2026},
  doi       = {10.5281/zenodo.22100743},
  url       = {https://github.com/plainbook-ai/plainbook},
  license   = {BSD-3-Clause}
}
```

To cite the design and the testing approach, cite the paper:

```bibtex
@article{plainbook-paper,
  title   = {Plainbook: Data Science, in Plain Language},
  author  = {de Alfaro, Luca and Aubert, Mathis and Jhala, Ranjit and
             Pastor, Eliana and Baralis, Elena},
  journal = {arXiv preprint arXiv:2607.05717},
  year    = {2026},
  doi     = {10.48550/arXiv.2607.05717}
}
```

## Contributors

To contribute to Plainbook, please see [CONTRIBUTING.md](CONTRIBUTING.md) for
the licensing terms, and [DEVELOP.md](DEVELOP.md) for development setup.

* [Luca de Alfaro](https://github.com/lucadealfaro), lead developer, UC Santa Cruz. 
* [Mathis Aubert](https://github.com/Maths-A), UC Santa Cruz. 
* [Ranjit Jhala](https://ranjitjhala.github.io/), UC San Diego. 
* [Dhyan Soni](). 
* [Uchechi Ejiogu]().
* [Eliana Pastor](https://elianap.github.io/), Politecnico di Torino.
* [Elena Baralis](https://www.polito.it/en/staff?p=elena.baralis), Politecnico di Torino.

## License

Plainbook is released under the [BSD 3-Clause license](LICENSE.md).
Contributions are accepted under the same license — see
[CONTRIBUTING.md](CONTRIBUTING.md).
