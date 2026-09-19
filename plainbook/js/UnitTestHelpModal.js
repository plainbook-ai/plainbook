export default {
    props: ['isActive'],
    emits: ['close'],
    template: /* html */ `
    <div class="modal" :class="{'is-active': isActive}">
        <div class="modal-background" @click="$emit('close')"></div>
        <div class="modal-card" style="width: 90%; max-width: 900px;">
            <header class="modal-card-head">
                <p class="modal-card-title">How to test a cell</p>
                <button class="delete" aria-label="close" @click="$emit('close')"></button>
            </header>
            <section class="modal-card-body">
                <div class="help-container p-5">
                    <div class="content">
                        <p>
                        The cell being tested is copied here as the <em>Target Cell</em>.
                        Testing it consists of three steps:
                        </p>
                        <ul>
                        <li><b>First</b>, in the <em>Data Preparation</em> cell, you prepare the data used to test the target cell.
                            <ul>
                            <li>Typically, you want to prepare some simple data, so you can make sense of it.</li>
                            <li>You can also prepare inputs that test edge cases, such as missing values, ties, etc.
                            </li>
                            </ul>
                        Just describe the data you want in English. 
                        Plainbook knows what the target cell needs, so it can create the right data for it.
                        <blockquote class="mt-3"><em>Example:</em> Generate a smaller dataset where each team plays once home, and once away.</blockquote>
                        </li>
                        <li class="mt-4"><b>Second</b>, the target cell is run.</li>
                        <li class="mt-4"><b>Finally</b>, you can visually inspect the results or use the Test Cell to define specific output checks. </li>
                        </ul>
                    </div>
                </div>
            </section>
            <footer class="modal-card-foot">
                <button class="button" @click="$emit('close')">Close</button>
            </footer>
        </div>
    </div>`
};
