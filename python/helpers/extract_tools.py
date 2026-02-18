import re, os, importlib, importlib.util, inspect, html
from types import ModuleType
from typing import Any, Type, TypeVar
from .dirty_json import DirtyJson
from .files import get_abs_path, deabsolute_path
import regex
from fnmatch import fnmatch

_MINIMAX_BLOCK_RE = re.compile(
    r"<minimax:tool_call>\s*(?P<body>.*?)\s*</minimax:tool_call>",
    flags=re.IGNORECASE | re.DOTALL,
)
_INVOKE_RE = re.compile(
    r"<invoke\s+name=(?P<q>['\"])(?P<name>[^'\"]+)(?P=q)\s*>(?P<body>.*?)</invoke>",
    flags=re.IGNORECASE | re.DOTALL,
)
_PARAM_RE = re.compile(
    r"<parameter\s+name=(?P<q>['\"])(?P<name>[^'\"]+)(?P=q)\s*>(?P<value>.*?)</parameter>",
    flags=re.IGNORECASE | re.DOTALL,
)

def json_parse_dirty(json:str) -> dict[str,Any] | None:
    if not json or not isinstance(json, str):
        return None

    ext_json = extract_json_object_string(json.strip())
    if ext_json:
        try:
            data = DirtyJson.parse_string(ext_json)
            if isinstance(data,dict): return data
        except Exception:
            # Fall back to alternate tool-call formats.
            pass

    xml_data = extract_minimax_tool_call(json)
    if xml_data:
        return xml_data
    return None


def extract_minimax_tool_call(content: str) -> dict[str, Any] | None:
    if not content or not isinstance(content, str):
        return None

    body = content
    block_match = _MINIMAX_BLOCK_RE.search(content)
    if block_match:
        body = block_match.group("body")

    invoke_match = _INVOKE_RE.search(body)
    if not invoke_match:
        return None

    tool_name = invoke_match.group("name").strip()
    invoke_body = invoke_match.group("body")
    if not tool_name:
        return None

    tool_args: dict[str, Any] = {}
    for param_match in _PARAM_RE.finditer(invoke_body):
        key = param_match.group("name").strip()
        if not key:
            continue
        raw_value = param_match.group("value")
        tool_args[key] = _coerce_minimax_param_value(raw_value)

    return {"tool_name": tool_name, "tool_args": tool_args}


def _coerce_minimax_param_value(value: str) -> Any:
    text = html.unescape(value or "").strip()
    if not text:
        return ""

    # Handle common MiniMax malformed values like python"
    if text.endswith('"') and text.count('"') % 2 == 1 and not text.startswith('"'):
        text = text[:-1].rstrip()
    if text.endswith("'") and text.count("'") % 2 == 1 and not text.startswith("'"):
        text = text[:-1].rstrip()

    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]

    lower = text.lower()
    if lower in {"true", "false", "null"}:
        try:
            return DirtyJson.parse_string(lower)
        except Exception:
            return text

    if text[0] in "{[":
        try:
            return DirtyJson.parse_string(text)
        except Exception:
            return text

    if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", text):
        try:
            return DirtyJson.parse_string(text)
        except Exception:
            return text

    return text

def extract_json_object_string(content):
    start = content.find('{')
    if start == -1:
        return ""

    # Find the first '{'
    end = content.rfind('}')
    if end == -1:
        # If there's no closing '}', return from start to the end
        return content[start:]
    else:
        # If there's a closing '}', return the substring from start to end
        return content[start:end+1]

def extract_json_string(content):
    # Regular expression pattern to match a JSON object
    pattern = r'\{(?:[^{}]|(?R))*\}|\[(?:[^\[\]]|(?R))*\]|"(?:\\.|[^"\\])*"|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'

    # Search for the pattern in the content
    match = regex.search(pattern, content)

    if match:
        # Return the matched JSON string
        return match.group(0)
    else:
        return ""

def fix_json_string(json_string):
    # Function to replace unescaped line breaks within JSON string values
    def replace_unescaped_newlines(match):
        return match.group(0).replace('\n', '\\n')

    # Use regex to find string values and apply the replacement function
    fixed_string = re.sub(r'(?<=: ")(.*?)(?=")', replace_unescaped_newlines, json_string, flags=re.DOTALL)
    return fixed_string


T = TypeVar('T')  # Define a generic type variable

def import_module(file_path: str) -> ModuleType:
    # Handle file paths with periods in the name using importlib.util
    abs_path = get_abs_path(file_path)
    module_name = os.path.basename(abs_path).replace('.py', '')
    
    # Create the module spec and load the module
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {abs_path}")
        
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def load_classes_from_folder(folder: str, name_pattern: str, base_class: Type[T], one_per_file: bool = True) -> list[Type[T]]:
    classes = []
    abs_folder = get_abs_path(folder)
    skip_missing_imports = os.getenv("A0_SKIP_MISSING_MODULE_IMPORTS", "").strip().lower() in {"1", "true", "yes", "on"}

    # Get all .py files in the folder that match the pattern, sorted alphabetically
    py_files = sorted(
        [file_name for file_name in os.listdir(abs_folder) if fnmatch(file_name, name_pattern) and file_name.endswith(".py")]
    )

    # Iterate through the sorted list of files
    for file_name in py_files:
        file_path = os.path.join(abs_folder, file_name)
        try:
            module = import_module(file_path)
        except ModuleNotFoundError as e:
            if not skip_missing_imports:
                raise
            print(f"Skipping module due to missing dependency: {file_name} ({e})")
            continue

        # Get all classes in the module
        class_list = inspect.getmembers(module, inspect.isclass)

        # Filter for classes that are subclasses of the given base_class
        # iterate backwards to skip imported superclasses
        for cls in reversed(class_list):
            if cls[1] is not base_class and issubclass(cls[1], base_class):
                classes.append(cls[1])
                if one_per_file:
                    break

    return classes

def load_classes_from_file(file: str, base_class: type[T], one_per_file: bool = True) -> list[type[T]]:
    classes = []
    # Use the new import_module function
    module = import_module(file)
    
    # Get all classes in the module
    class_list = inspect.getmembers(module, inspect.isclass)
    
    # Filter for classes that are subclasses of the given base_class
    # iterate backwards to skip imported superclasses
    for cls in reversed(class_list):
        if cls[1] is not base_class and issubclass(cls[1], base_class):
            classes.append(cls[1])
            if one_per_file:
                break
                
    return classes
