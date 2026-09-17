# <img src="https://github.com/plainbook-ai/plainbook/raw/main/plainbook/images/Plainbook_logo.png" height="30"> Plainbook: Natural Language Notebooks

Plainbooks are computational notebooks written in natural language, so anyone can read and modify them, without requiring coding knowledge. 

Plainbooks aim at replicating what made [Jupyter notebooks](https://jupyter.org/) successful, namely the ability to create and share reproducible data analysis, while broadening their audience beyond people familiar with coding. 

The main features of Plainbook are: 
- **Natural language:** Describe what you want in plain English; AI generates and validates the code. 
- **Multiple AI providers:** Generate and validate code using either cloud models from Gemini, Claude, or OpenAI, or free open-weights local models running on your own computer. 
- **Built-in testing:** You can test cells with data, to check that the code correctly implements the natural language.
- **Shareable & reproducible:** Anyone who can understand natural language can make sense of your notebooks, and adapt them to their own data and needs.

You can read more about the design philosophy of Plainbook, and its code testing approach, in the paper [Plainbook: Data Science, in Plain Language](https://arxiv.org/abs/2607.05717). 


## Try Plainbook Now

**Videos**
* [30-second demo](https://youtu.be/0t4ND8wPoYA)
* [5-minute introduction](https://youtu.be/Mkv5cl5rA7s)

**Run on GitHub Codespaces (no installation needed):**
1. Click **Code** → **Codespaces** in the GitHub interface
2. Wait ~3 minutes for the environment to set up
3. Click **Open in Browser** for port 8080; the Soccer World Cup example is already open
4. A trial Claude API key is provided; you can add your own in Settings

**Example Notebooks**

<a href="https://github.com/plainbook-ai/plainbook/raw/main/plainbook/images/SoccerExample.png"><img src="https://github.com/plainbook-ai/plainbook/raw/main/plainbook/images/SoccerExample.png" width="420" title="Click to enlarge" alt="A plainbook analyzing soccer World Cup data, showing plain-language cells next to the code generated from them"></a>

<sub><a href="https://github.com/plainbook-ai/plainbook/raw/main/plainbook/images/SoccerExample.png">&#128269; Click the image to enlarge it</a></sub>

* [getting_started.plnb](https://github.com/plainbook-ai/plainbook/raw/main/examples/getting_started.plb) — three short cells; the place to start.
* [Soccer_w_Tests.plnb](https://github.com/plainbook-ai/plainbook/raw/main/examples/Soccer_w_Tests.plnb) — demonstrates action cells, tests, and AI validation.

To try one, save the file, then open it with Plainbook:

```bash
plainbook Soccer_w_Tests.plnb
```

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

Installing Plainbook gives you the notebook environment, but not the data-science packages themselves: pandas, matplotlib and the like are not pulled in.
You do not need to install them in advance, though.
When a cell's generated code imports a package that is not present, Plainbook says so and offers to install it for you, or to rewrite the code without it.



## Plainbook Structure

Plainbooks consist of three types of cells: 

* **Action cells**, where the user describes in natural language the action to be performed (e.g., "Load the dataset from file data.csv and display the first 10 rows").  The system converts the description to code, executes it, and displays the results below the cell.

* **Comment cells**, where the user can add comments, section headers, and so forth, using markdown syntax. 

* **Test cells**, where the user can write properties that should hold at certain points of the notebook to check that everything is working as expected.

You can also create **unit tests** for Plainbook cells. These tests generate simple data and feed it to the notebook cells you want to test, enabling you to check that the code generated from natural language is correct.  

## Working with Notebooks

Alongside the cells, three notebook-wide tools are available from the navbar and from the panel above the first cell.

**Accessing files**

You can use the **Files** panel allows you to select the data files that will be used in the notebook. 

**Verification**

You can use a **verify** button in the navbar to ask the AI to audit the notebook as a whole.
For every cell it checks two things: that the code really does what the cell's explanation says, and that the code does nothing dangerous.

**AI Instructions**

The **Instructions** panel holds guidance that is appended to every code-generation request in that notebook — for example, "always label the axes of plots", or "prefer polars over pandas".

**Linear Execution**

Unlike standard Jupyter notebooks (and like [Marimo](https://marimo.io)), Plainbook cells are guaranteed to be executed in order, from first to last, matching the order in which humans read the cells. 
Plainbook relies on a [checkpointing kernel](https://github.com/plainbook-ai/snapshot-kernel) to remember the execution state after each cell, so that it can re-run a cell without having to start from the beginning.  

## AI Models

Plainbook needs an AI model to generate and validate code.  You can use: 

* **Local open-weights model** (gpt-oss:20b via Ollama).  
Go to Settings, under Local Models, click *Download & set up*.  
This works (tested) on a MacBook Air M3 with 24GB of memory, and may work well on other computers with at least 16GB of memory.  
Code generation is slower than with cloud models, but it is free and private. 

* **Gemini, Claude, or OpenAI** cloud models. Go to Settings, and add one or more API keys.  To obtain API keys, follow the links for the model vendors.

You can easily switch between the models in the AI model dropdown in the navbar. 

If you choose to use a local model, Plainbook downloads the [Ollama](https://ollama.com) runtime into `~/.config/plainbook/ollama/` (no administrator rights needed; about 160 MB on macOS, 1.4 GB on Linux and Windows, or it uses an Ollama you already have) and then the model, `gpt-oss:20b` (about 14 GB, kept in Ollama's usual `~/.ollama/models`). 
The model needs a computer with at least 16 GB of memory. Once set up, choose *Local: GPT-OSS 20B* from the AI model dropdown in the navbar. 
The model is loaded when you select it and unloaded when you switch to a cloud model or close Plainbook. 
Local models are slower and less capable than the cloud ones, but they are a way to try Plainbook, and to work privately, at no cost. 
*Remove* in Settings deletes the model from your disk.

## Papers

* L. de Alfaro, M. Aubert, R. Jhala, E. Pastor, E. Baralis. [_Plainbook: Data Science, in Plain Language_](https://arxiv.org/abs/2607.05717), July 2026.


To cite Plainbook, you can cite [the software](https://github.com/plainbook-ai/plainbook/blob/main/doc/plainbook-software.bib), or [the paper](https://github.com/plainbook-ai/plainbook/blob/main/doc/plainbook-paper.bib).

## Resources

* [GitHub Repository](https://github.com/plainbook-ai/plainbook).
* [Pypi package](https://pypi.org/project/plainbook/).
* [Development mailing list](https://groups.google.com/g/plainbook).

## Contributors

To contribute to Plainbook, please see [CONTRIBUTING.md](https://github.com/plainbook-ai/plainbook/blob/main/CONTRIBUTING.md) for the licensing terms, and [DEVELOP.md](https://github.com/plainbook-ai/plainbook/blob/main/DEVELOP.md) for development setup.

* [Luca de Alfaro](https://github.com/lucadealfaro), lead developer, UC Santa Cruz. 
* [Mathis Aubert](https://github.com/Maths-A), UC Santa Cruz. 
* [Ranjit Jhala](https://ranjitjhala.github.io/), UC San Diego. 
* [Dhyan Soni](https://github.com/dhyantsoni). 
* [Uchechi Ejiogu](https://github.com/zuchichi).
* [Eliana Pastor](https://elianap.github.io/), Politecnico di Torino.
* [Elena Baralis](https://www.polito.it/en/staff?p=elena.baralis), Politecnico di Torino.

## License

Plainbook is released under the [BSD 3-Clause license](https://github.com/plainbook-ai/plainbook/blob/main/LICENSE.md).
Contributions are accepted under the same license — see [CONTRIBUTING.md](https://github.com/plainbook-ai/plainbook/blob/main/CONTRIBUTING.md).
