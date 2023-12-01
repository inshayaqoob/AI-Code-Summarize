import re
import tokenize as py_tokenize
import token as py_token
from io import BytesIO


class Preprocess:
    def __init__(self, mode):
        assert mode in ['anno', 'code', 'docs']
        self.mode = mode

    def tokenize_python(self, snippet: str):
        toks = py_tokenize.tokenize(
            BytesIO(snippet.strip().encode('utf-8')).readline)

        def predicate(t):
            return py_token.tok_name[t.type] not in \
                ['ENCODING', 'NEWLINE', 'ENDMARKER', 'ERRORTOKEN']
        return [t.string for t in toks if predicate(t)]

    def clean(self, x):
        x = re.sub(r'[‘…—−–]', ' ', x)
        x = re.sub(r'[?，`“”’™•°]', '', x)

        if self.mode == 'anno' or self.mode == 'docs':
            x = re.sub(r'[,:;]', r'', x)
            x = re.sub(r'([\+\-\*/=(){}%^&\.])', r' \1 ', x)
            x = re.sub(r'\.+$', r'', x)

        if self.mode == 'docs':
            x = re.sub(r'[\t\r\n\v\f]', r'', x)
            x = re.sub(r'[\(\[\]\)]', r'', x)

        if self.mode == 'code':
            x = re.sub(r'[\(\[\+\-\*/,:;=(){}%^&\]\)\'\"]', r'', x).strip()
            # x = re.sub(r"([])':;{}%^&|")
            # row = re.sub(r'[\[\]\(\)]', '', row).strip()
            x = ' '.join(x.split())
            x = ' '.join(self.tokenize_python(x))

        x = re.sub(r'[ ]+', ' ', x)
        x = x.strip()
        return x

    def tokenize(self, x):
        if self.mode == 'anno':
            # TODO: something smarter?
            # return [tok.text for tok in nlp.tokenizer(x)]
            return x.split()

        if self.mode == 'code':
            return x.split()
