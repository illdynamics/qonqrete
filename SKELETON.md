# Code Skeletonization in QonQrete (Qompressor)

Code skeletonization in QonQrete is a core process implemented by the `worqer/qompressor.py` agent. Its primary purpose is to transform a full codebase into a highly token-efficient, structural representation, often referred to as a "skeleton" or "qompressed" code. This process is crucial for managing the context provided to Large Language Models (LLMs), including Qwen, and significantly reducing processing costs and improving relevance.

## How Skeletonization Works (`qompressor.py`)

The `qompressor` agent takes a source directory (typically `worqspace/qodeyard`) and processes its files into a destination directory (typically `worqspace/bloq.d`).

### 1. File Classification

`qompressor` classifies files into three categories:

*   **Files to 'Skeletonize' (`COMPRESS_EXTENSIONS`):** These are typically source code files in languages like Python, JavaScript, TypeScript, Go, Rust, Java, C/C++, PHP. For these files, the implementation bodies are stripped, but their architectural and interface-defining elements are preserved.
*   **Files to Copy 'As-Is' (`COPY_EXTENSIONS`):** These include configuration files (`.yaml`, `.json`, `.toml`), markdown documents (`.md`), and plain text files (`.txt`). Their full content is preserved because it's often directly relevant context with a relatively low token count.
*   **Special Filenames to Copy 'As-Is' (`COPY_FILENAMES`):** Specific files like `Dockerfile`, `Makefile`, `Jenkinsfile`, etc., are also copied without modification as their full content is often critical.

### 2. Compression Logic

The core of skeletonization lies in the content compression:

*   **Python (`compress_python`):**
    *   Utilizes Python's `ast` (Abstract Syntax Tree) module for robust parsing. This allows for precise identification and retention of structural elements.
    *   **What is Kept:**
        *   `import` statements (e.g., `import os`, `from pathlib import Path`)
        *   `class` definitions (e.g., `class MyClass(BaseClass):`)
        *   `function` definitions (e.g., `def my_function(arg1: str) -> bool:`)
        *   `async def` definitions
        *   Docstrings for classes and functions
        *   Decorators
        *   Comments
    *   **What is Stripped:** The entire implementation body of functions and methods, replaced with a placeholder comment (`# ... (body stripped by Qompressor) ...`).
*   **Generic (`compress_generic`):**
    *   For other languages, a regex-based approach is used, which is less precise but still effective for providing structural hints.
    *   **What is Kept (heuristically):** Lines containing comments, structural keywords (e.g., `function`, `class`, `func`, `def`, `struct`, `pub `, `import `), or lines ending with `{` or `}`.
    *   **What is Stripped:** Most of the internal logic and statements that do not define structure or interface.

### 3. Output Management

*   The destination directory (`bloq.d`) is completely cleared and rebuilt each time `qompressor` runs, ensuring that the skeletons are always up-to-date with the `qodeyard`.
*   The relative directory structure from `qodeyard` is maintained in `bloq.d`.

## Role in Context and Memory

Code skeletonization plays a dual role in both QonQrete's memory and context mechanisms:

### As Context:
*   **Architectural Overview:** The `bloq.d` directory serves as a high-level architectural context for LLMs. It allows them to quickly grasp the project's structure, available modules, classes, and function interfaces without needing to parse and understand every line of code.
*   **Efficient Prompting:** By providing only the essential structural information, `qompressor` drastically reduces the token count required to represent the codebase. This frees up valuable context window space for the LLM to process more critical task-specific instructions, semantic summaries, or problem details. This makes the LLM more efficient and less prone to "forgetting" earlier parts of the prompt.
*   **Targeted Code Generation:** When an LLM is tasked with generating new code or modifying existing code, the skeletons provide the necessary function signatures, class structures, and dependencies to ensure the generated code integrates correctly with the existing system.

### As Memory:
*   **Structural Memory:** `bloq.d` acts as a structural memory of the `qodeyard`. It's a persistent, indexed representation of the codebase's architecture. This memory is "read-only" in the sense that agents do not directly modify `bloq.d`; rather, `qompressor` regenerates it as needed from `qodeyard`.
*   **Foundation for Semantic Memory:** The skeletonized code from `bloq.d` is a crucial input for the `qontextor` agent. `qontextor` uses these skeletons (via `lib_ai.py`'s `_build_prompt` mechanism) to generate the richer, semantic context stored in `qontext.d`. In this way, skeletonization forms the structural foundation upon which the system's semantic understanding (memory) is built.

## Conclusion

The `qompressor` and the `bloq.d` directory are fundamental to QonQrete's ability to efficiently and effectively interact with LLMs. By intelligently reducing the verbosity of the codebase while preserving its architectural essence, skeletonization ensures that LLMs receive a focused and optimized view of the project's structure, enabling more accurate and token-efficient reasoning and code generation. It is a zero-token-cost way to retain code architecture.
