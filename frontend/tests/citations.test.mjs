import test from 'node:test';
import assert from 'node:assert/strict';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import { citationAnchors } from '../src/lib/citationAnchors.ts';

function render(source, emitIds = true) {
  const processor = unified().use(remarkParse).use(citationAnchors, { emitIds }).use(remarkRehype);
  return processor.runSync(processor.parse(source));
}
function elements(tree) {
  return [tree, ...(tree.children ?? []).flatMap(elements)].filter(node => node.type === 'element');
}

test('real Markdown parser preserves APA destinations and hanging-indent class', () => {
  const nodes = elements(render('<a id="ref-smith-2020"></a>Smith, A. (2020). Study.'));
  assert.ok(nodes.some(node => node.properties.id === 'ref-smith-2020'));
  assert.ok(nodes.some(node => node.properties.className === 'apa-reference'));
});
test('excerpt rendering avoids duplicate citation destinations', () => {
  const nodes = elements(render('<a id="cite-ref-smith-2020-1"></a>[Smith, 2020](#ref-smith-2020)', false));
  assert.equal(nodes.filter(node => node.properties.id).length, 0);
  assert.ok(nodes.some(node => node.properties.href === '#ref-smith-2020'));
});
test('arbitrary HTML is not enabled by the anchor plugin', () => {
  const nodes = elements(render('<a id="ref-smith" onclick="alert(1)"></a>Text'));
  assert.equal(nodes.filter(node => node.properties.id).length, 0);
});
