"""Static documentation extraction; browser CSS difference remains explicit."""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('documentation_page_text', ROOT/'scripts/page_text.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_python_method_definition():
    html=(ROOT/'fixtures/page_text/python-method.html').read_text(encoding='utf-8')
    observed=module.page_text(html,url='https://docs.python.org/3/library/html.parser.html')
    assert observed['truncated'] is False
    words=observed['text'].split()
    assert words[0]=='HTMLParser.feed(data)¶'
    assert ' '.join(words[1:])=='Feed some text to the parser. It is processed insofar as it consists of complete elements; incomplete data is buffered until more data is fed or close() is called. data must be str.'
    links=module.find_elements(html,'close',url='https://docs.python.org/3/library/html.parser.html')
    assert any(link.get('href')=='https://docs.python.org/3/library/html.parser.html#html.parser.HTMLParser.close' for link in links)
