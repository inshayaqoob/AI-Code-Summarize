import argparse
import ast
import asttokens
import os
import re
import shutil
import tokenize
from ast_conversion import get_dfs, convert
from io import BytesIO
from processor_ast import Preprocess
from subprocess import DEVNULL, STDOUT, run
from typing import Tuple, List

import json
import parse_python3

# Creating exclude tokens for excluding punctuation
import string
EXCLUDE_TOKENS = set(string.punctuation)

SPACE_STOPWORDS = [' ', '\t', '\r', '\n', '\v', '\f']
TOKENS_STOPWORDS = SPACE_STOPWORDS + ["utf-8"]
DOCSTRING_PREFIX = "###DCSTR### "


class CommentProcessor:
    """
    Stores every comment from a given code file
    self.comments: lineno -> comment string
    self.code_without: code without comments
    """
    def __init__(self):
        self.comments = {}
        self.code_without = ""

    def parse_comments(self, code: str):
        """
        Prepares comments and save into self.comments dict.
        ---
        code: string, represents python's code
        """
        for lineno, line in enumerate(code.split("\n")):
            code_line = line
            if '#' in line:
                comment = line[line.find('#') + 1:]
                line = line[:line.find('#')]
                quotes1 = line.count('"')
                quotes2 = line.count("'")
                # comment = tiny_filter(comment)
                if len(comment) and quotes1 % 2 == 0 and quotes2 % 2 == 0:
                    self.comments[lineno] = comment
                code_line = line[:line.find("#")]
            if len(code_line) > 0:
                self.code_without += f"{code_line}\n"


def read_file_to_string(filename: str) -> str:
    """
    Reading file contents into string object
    """
    f = open(filename, 'rt')
    s = f.read()
    f.close()
    return s


def get_tokens(code: str) -> Tuple[list, int, list]:
    """
    code: str,
        Represents Python's file in string.
    ---
    Returns:
        tokens: List[str]
            List of tokens in the current function
        comments: List[str]
            List of retrieved comments
        docstring: str or None
            Found docstring or None
        stopwords_count: int
            A number of stopwords in the current piece of code
    """
    global TOKENS_STOPWORDS
    tokens = []
    # comment_ind = 0

    double_format = True
    ds_begin = code.find('"""')
    if ds_begin == -1:
        double_format = False
        ds_begin = code.find("'''")
    ds_end = code.find('"""', ds_begin + 3)
    if not double_format:
        ds_end = code.find("'''", ds_begin + 3)

    docstring = None
    if ds_begin != -1 and ds_end != -1:
        docstring = code[ds_begin + 3:ds_end].strip()

    # Erase docstring from the code
    if ds_begin != -1 and ds_end != -1:
        code = code[:ds_begin] + code[ds_end + 3:]

    # Handle comments with a CommentsProcessor instance
    processor = CommentProcessor()
    processor.parse_comments(code)
    code = processor.code_without

    # Let's fulfil returning comments by looking at processor state
    comments = list(processor.comments.values())

    stopwords_count = 0
    is_tokenizable = True

    try:
        for idx, token in enumerate(
                tokenize.tokenize(BytesIO(code.encode('utf-8')).readline)):
            # Form indices and tokens
            if token.string not in TOKENS_STOPWORDS:
                # print(f"idx: {idx}, token: {token.string}")
                tokens.append(token.string)
            else:
                stopwords_count += 1
    except:
        is_tokenizable = False
        return None, None, comments, docstring, stopwords_count, is_tokenizable
    return code, tokens, comments, docstring, stopwords_count, is_tokenizable


def get_previous_comments(fun: ast.FunctionDef, code_lines: List[str]) -> str:
    """
    Returns a comment on the line above the function definition.
    ---
    fun: ast.FunctionDef,
        Function object.
    code_lines: str,
        Special index to be put in node.id ?
    """
    fun_line_first = fun.first_token.start[0] - 1

    comment_line = code_lines[fun_line_first - 1].strip()
    zero_line = code_lines[fun_line_first - 2].strip()

    precomment = ""
    if (len(comment_line) > 0) and (comment_line[0] == "#"):
        if (fun_line_first >= 2 and len(comment_line) >= 1
                and zero_line == "") or (fun_line_first == 1
                                         and len(comment_line) >= 1):
            precomment = code_lines[fun_line_first - 1].strip()
    return precomment


error_counter = 0


def collect_data(filename: str,
                 args: argparse.ArgumentParser) -> List[List[str]]:
    """
    Read an 2 unparallel corpuses: functions and docstrings.
    ---
    Returns:
        data: List[List[str]]
            Summarized data from functions.
        is_appropriate: bool
            A flag indicating that the file is appropriate
            (enough scope size or no errors in parsing).
    """
    global error_counter

    # Convert Python 2 to Python 3
    # os.system(f"~/anaconda3/envs/scs/bin/2to3 {filename} -w -n")
    # run(["/home/masaidov/.conda/envs/scs/bin/2to3", filename, "-w", "-n"],
    #     stdout=DEVNULL, stderr=STDOUT)
    run(["/home/marat/anaconda3/envs/scs-ext/bin/2to3", filename, "-w", "-n"],
        stdout=DEVNULL, stderr=STDOUT)
    print("Building AST tree from a filename:", filename)

    try:
        code = read_file_to_string(filename)
    except:
        print("File with bad encoding:", filename)
        error_counter += 1
        is_appropriate = False
        return None, is_appropriate

    # let's replace tabs for spaces in the future
    code = re.sub('\t', ' ' * 4, code)

    code_lines = code.splitlines()

    try:
        atok = asttokens.ASTTokens(code, parse=True)
        astree = atok.tree
    except:
        print("Files with an error:", error_counter)
        error_counter += 1
        is_appropriate = False
        return None, is_appropriate

    data = []

    # Global loop: iterating over functions from file
    for fun_ind, fun in enumerate(ast.walk(astree)):
        if isinstance(fun, ast.FunctionDef) and len(fun.body) > 0:
            fun_begin = fun.first_token.startpos
            fun_end = fun.last_token.endpos
            prev_comment = get_previous_comments(fun, code_lines)
            docstring = ast.get_docstring(fun)
            if not docstring:
                docstring = ""
            else:
                docstring = DOCSTRING_PREFIX + docstring + "\n"

            # Forming scope -- set of node ids (variables)
            scope = [arg.arg for arg in fun.args.args]
            for node in ast.walk(fun):
                if isinstance(node, ast.Name) and \
                   isinstance(node.ctx, ast.Store):
                    scope.append(node.id)
            scope = set(scope)

            if len(scope) < 2:
                # print(f"Note: Function with fun.name = {fun.name} has too "
                #       "small scope.")
                continue

            function_code = code[fun_begin:fun_end]

            # if met @classmethod keyword,
            # should relax tabulation
            start_def = function_code.find("def")
            function_code = function_code[start_def:]

            function_code, tokens, comments, docstring, stopwords_count, \
                is_tokenizable = get_tokens(function_code)

            if not is_tokenizable:
                error_counter += 1
                function_code = ""
                tokens = []

            # print(f"In filename = {filename}, fun_ind = {fun_ind}")
            # print(f"Found {stopwords_count} stopwords.")

            if len(prev_comment) > 0:
                comments = [prev_comment] + comments

            data.append([filename, function_code, tokens, comments, docstring])

    is_appropriate = len(data) > 0
    return data, is_appropriate


def retrieve_functions_docstrings(
        data: List, args: argparse.ArgumentParser) -> List[List[str]]:
    """
    add description
    ---
    Returns:
        comments: List[str],
            Functions comments separately.
        docstrings: List[str],
            Tokenized docstring corpus.
        functions: List[str],
            Tokenized function corpus.
        ord_nodes: List[*]
            Data consists of (node.id, token ind, remember ind)
            objects for further masking and processing.
        ast_tokens: List[str],
            Functions content with AST post-processing.
        text_tokens: List[str],
            Functions without AST post-processing.
    """

    preprocess_code = Preprocess("code")
    preprocess_comment = Preprocess("anno")
    preprocess_docstring = Preprocess("docs")

    comments = []
    docstrings = []
    functions = []
    ord_nodes = []
    tokens = []

    for filename, code, fun_tokens, fun_comments, docstring in data:
        # Add asserts for debugging
        assert type(code) == str, "code variable is not a string"
        assert type(fun_tokens) == list, \
            "fun_tokens variable is not a list"
        assert type(fun_comments) == list, \
            "fun_comments variable is not a list"

        # Let's preprocess every found comment
        for comment in fun_comments:
            if len(comment) <= 3:
    
                continue
            comment = preprocess_comment.clean(comment).replace("'",
                                                                " ").replace(
                                                                    '"', " ")
            comment = comment[:comment.find(".")]
            comment = ''.join(ch for ch in comment if ch not in EXCLUDE_TOKENS)
            comment = ' '.join(comment.split()) + " ."
            comments.append(comment)

        # Let's preprocess function tokens
        fun_tokens_string = ' '.join(fun_tokens)
        fun_tokens_string = preprocess_code.clean(fun_tokens_string)

        functions.append(code)
        tokens.append(fun_tokens_string)

        if docstring is not None:
            docstring = preprocess_docstring.clean(docstring).strip()
            if len(docstring) > 0:
                docstrings.append(docstring)

    return comments, docstrings, functions, ord_nodes, tokens


def find_nth(haystack, needle, n):
    start = haystack.find(needle)
    while start >= 0 and n > 1:
        start = haystack.find(needle, start+len(needle))
        n -= 1
    return start


def set_script_arguments(parser):
    # Main arguments
    main_args = parser.add_argument_group("Main")
    main_args.add_argument("--dirname",
                           type=str,
                           default="/home/marat/source-code-data/python150k-demo",
                           help="Python150k storage.")
    main_args.add_argument("--code_output",
                           type=str,
                           default="python150k_code.json",
                           help="Output location for code.")
    main_args.add_argument("--docs_output",
                           type=str,
                           default="python150k_docs.json",
                           help="Output location for docstrings.")
    main_args.add_argument("--location",
                           type=str,
                           default="json",
                           help="A folder for output files storage.")
    return


def main(args):
    global error_counter
    # Clear the convertation directory
    if os.path.exists(args.location):
        shutil.rmtree(args.location)
    os.mkdir(args.location)
    print("Created directory:", args.location)

    # Handling suffixes
    suffix = args.dirname[args.dirname.rfind('/') + 1:]

    file_cnt = 0

    code_file = open(os.path.join(args.location, args.code_output), "a")
    docs_file = open(os.path.join(args.location, args.docs_output), "a")
    print("Opened output files...")

    for root, _, fnames in sorted(os.walk(args.dirname)):
        # print("root =", root)
        for fname in fnames:
            # print("Handling fname =", fname)
            if fname.endswith(".py"):
                print("Handling fname =", fname)
                filename = os.path.join(root, fname)

                data, is_appropriate = collect_data(filename, args)
                if not is_appropriate:
                    continue
                comments, docstrings, functions, ord_nodes, tokens = \
                    retrieve_functions_docstrings(data, args)

                ### Change of preprocess.py for JSON creation ###

                repo_path = filename[filename.rfind(suffix) + len(suffix) + 2:]
                slash_ind = find_nth(repo_path, "/", 2)
                repo_name = repo_path[:slash_ind]
                inner_path = repo_path[slash_ind + 1:]

                print("~" * 50)
                print(f"Handling repository: {repo_path}...")
                print(f"Handling file: {fname}...")

                code_buffer = ""
                for code in functions:
                    code_buffer += f"{code}\n\n"

                # Form JSON for code
                code_contents = {
                    "repo_name": repo_name,
                    "ref": "refs/heads/master",
                    "path": inner_path,
                    "content": code_buffer,
                }

                dcs_cnt = 0
                for docstring in docstrings:
                    if docstring is not None:
                        dcs_cnt += 1
                        # Form JSON for docstring
                        docs_contents = {
                            "repo_name": f"{repo_name}_number_{dcs_cnt}",
                            "ref": "refs/heads/master",
                            "path": inner_path,
                            "content": docstring,
                        }

                        # Append JSONs to proper files
                        json.dump(docs_contents, docs_file)
                        docs_file.write("\n")

                # Append JSONs to proper files
                json.dump(code_contents, code_file)
                code_file.write("\n")

                ### End of change ###

                file_cnt += 1
                print(
                    "Processed/Canceled/Total files:",
                    f"{file_cnt}/{error_counter}/{file_cnt + error_counter}")
                print("~" * 50)

    code_file.close()
    docs_file.close()

    return


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        'Python150k preparation',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    set_script_arguments(parser)
    args, unknown = parser.parse_known_args()
    print(args)
    main(args)
