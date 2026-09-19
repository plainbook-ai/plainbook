const NotebookHelp = {
    template: /* html */ `
        <div class="help-container p-5">
            <div class="content">
                <p>A Plainbook consists in a sequence of cells:</p>
                <ul>
                    <li><strong>Action cells:</strong> Describe what you want to do; Plainbook will generate and execute the code for you.</li>
                    <li><strong>Comment cells:</strong> You can use markdown to write comments and explanations.</li>
                </ul>
                <p><strong>Plainbook needs an AI model to generate and validate code.</strong> In the settings menu you can either set up a local model, which is free and private, or add an API key for Gemini, Claude or OpenAI.</p>

                <h2 class="title is-4">Working with Action Cells</h2>
                <ul>
                    <li><strong>Run:</strong> Click the play button to execute the notebook up to the current cell.  
                    Any missing code is generated before the cells are run.</li>
                    <li><strong>Regenerate Code:</strong> Ask AI to generate or fix code based on your description.</li>
                    <li><strong>Validate Code:</strong> Check if the generated code matches your description. You can use one AI
                    to check on the work of another.</li>
                    <li><strong>Move and Delete:</strong> Use arrow buttons to reorder cells, and the trash icon to delete them.</li>
                </ul>
                <p><strong>Execution order:</strong> Unlike in Jupyter Notebooks, cells are always guaranteed to be executed in order, starting from the beginning.
                If you click "Run" on a cell, all preceding cells will be executed first to ensure that the notebook 
                is always in a consistent state.</p>

                <h2 class="title is-4">Buttons and Settings</h2>
                <ul style="list-style: none; padding-left: 0;">
                <li class="mb-2"><button class="button is-small is-light"><i class="bx bx-lock-open"></i></button> 
                Toggles between read-only and editable modes.</li>
                <li class="mb-2"><button class="button is-small is-light"><i class="bx bx-broom"></i></button> 
                Clear all outputs.</li>
                <li class="mb-2"><button class="button is-small is-primary"><i class="bx bx-rewind"></i></button> 
                Reset the execution state, so that you can rerun the notebook from the start.</li>
                <!-- <li class="mb-2"><button class="button is-small is-primary"><i class="bx bx-keyframe-ease-in"></i></button> 
                Run the notebook from the beginning to the end.</li> -->
                <li class="mb-2"><button class="button is-small is-primary"><i class="bx bx-play"></i></button> 
                Run all cells (except tests).</li>
                <li class="mb-2"><button class="button is-small is-warning"><i class="bx bx-seal-check"></i></button> 
                Run all tests.  Tests are not run when you run the notebook.</li>
                <li class="mb-2"><button class="button is-small is-success"><i class="bx bx-shield"></i></button> 
                Toggles whether cell output is shared with AI (check not shown) or not (check shown).  
                If you are working with sensitive data, you may not want to share the cell outputs with AI. 
                Sharing the outputs with AI helps generate better code, and is the default setting for a notebook.</li>
                <li class="mb-2"><button class="button is-small is-light"><i class="bx bx-light-bulb"></i></button> 
                This dropdown allows you to switch between different AI models, including a
                model running on your own computer once you set one up in Settings (no API key needed).</li>
                </ul>
                

                <h2 class="title is-4">Reading Files</h2>
                <p>To read a file, first select it using the file manager at the top.  
                Then, you can refer to the file in your instructions using its name.
                This is done because if you simply cited a file name, AI would not be able to locate it 
                in your file system!</p>
                <p>The tab contains an indication of how many files you have selected. 
                In red are indicated files that cannot be found in the file system; pleaes re-select them. </p>

                <h2 class="title is-4">Testing Your Work</h2>
                <p>There are two ways to test your work.</p>
                <p><strong>Global test cells:</strong> You can insert test cells to verify the results of the preceding cell, 
                or to perform more complex checks referencing multiple previous cells.</p>
                <p><strong>Testing individual cells:</strong> You can also test individual cells by preparing 
                specific data for them, running the cell, and inspecting or testing the results.  
                This is especially useful when working with data, as you can test both normal data and edge cases.</p>

                <h2 class="title is-4">Instructions</h2>
                <p>In the instructions tab, you can write global instructions to be used in generating code. 
                You can include here information on APIs to use, and so on. </p>

                <h2 class="title is-4">Tips for Best Results</h2>
                <ul>
                    <li>Write clear, detailed descriptions of what you want the code to do.</li>
                    <li>If the generated code isn't right, update the description and regenerate.</li>
                </ul>

                <h2 class="title is-4">The Plainbook Project</h2>
                <p>Plainbook is open source.  You can visit the 
                <a href="https://github.com/lucadealfaro/plainbook" target="_blank">project 
                home page</a>, and install it as a 
                <a href="https://pypi.org/project/plainbook/" target="_blank">Python package</a>. </p>

            </div>
        </div>
    `
};

export default NotebookHelp;
