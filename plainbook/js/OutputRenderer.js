// OutputRenderer.js

import { isWarningOnlyStderr } from './errorUtils.js';

export default {
    props: ['output'],
    computed: {
        // stderr carrying a real failure keeps the danger colours; a stream that
        // only warns gets red on a light orange ground, so an advisory reads as
        // one. stdout is ordinary output text.
        streamClass() {
            if (this.output.name !== 'stderr') return 'output-text';
            return isWarningOnlyStderr(this.output)
                ? 'has-text-danger bg-warning-adaptive p-2'
                : 'has-text-danger has-background-danger-light p-2';
        }
    },
    methods: {
        join(src) { return Array.isArray(src) ? src.join('') : src; },

        ansiToHtml(lines) {
            const text = this.join(lines);
            const ansiMap = {
                '1': 'font-weight: bold;',
                '30': 'color: var(--bulma-text);',
                '31': 'color: #e3342f;', // Red
                '32': 'color: #38c172;', // Green
                '33': 'color: #f6993f;', // Yellow
                '34': 'color: #3490dc;', // Blue
                '35': 'color: #9561e2;', // Magenta
                '36': 'color: #4dc0b5;', // Cyan
                '37': 'color: white;',
                '39': '', // Reset foreground
                '0': 'font-weight: normal;' // Reset all
            };
            // This regex finds the ANSI escape codes: \u001b[...m
            return text.replace(/\u001b\[([\d;]+)m/g, (match, code) => {
                const codes = code.split(';');
                let style = '';
                codes.forEach(c => {
                    if (ansiMap[c]) style += ansiMap[c];
                });
                return style ? `</span><span style="${style}">` : '</span><span>';
            }).replace(/^<\/span>/, '') + '</span>';
        }
    },
    template: /* html */ `
        <div class="output-zone mb-2">
            <div class="output-container mt-1">
                <pre v-if="output.output_type === 'stream'"
                     :class="streamClass"
                     class="output-stream is-family-monospace is-size-7 whitespace-pre-wrap"
                     v-html="ansiToHtml(output.text)"></pre>

                <div v-else-if="output.output_type === 'error'">
                    <div class="has-text-danger has-text-weight-bold mb-2">
                        {{ output.ename }}: {{ output.evalue }}
                    </div>
                    <pre class="is-family-monospace is-size-7 whitespace-pre-wrap has-text-danger" 
                         v-html="ansiToHtml(output.traceback)"></pre>
                </div>  

                <div v-else-if="output.data">
                    <div v-if="output.data['text/html']"
                        class="html-output"
                        v-html="join(output.data['text/html'])"
                        style="overflow-x: auto; -webkit-overflow-scrolling: touch; max-width: 100%;">
                    </div>
                    <figure v-else-if="output.data['image/png']" class="image output-image"
                            style="display: inline-block; max-width: 100%; width: auto;">
                        <img :src="'data:image/png;base64,' + output.data['image/png']"
                             style="max-width: 100%; height: auto; display: block;">
                    </figure>
                    <pre v-else-if="output.data['text/plain']" 
                         class="output-text is-size-7 is-family-monospace">{{ join(output.data['text/plain']) }}</pre>
                </div>
            </div>
        </div>
    `
};
