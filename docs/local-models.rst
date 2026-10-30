Local models on Apple silicon
=============================

Run GGUF models with the installed ``llama.cpp`` tools, or use MLX and
``mlx-lm`` from a separate Python environment. These examples were checked on
an Apple silicon Mac with 64 GB of memory. Model inference runs locally after
the model files have been downloaded.

The first run downloads model files from Hugging Face and requires network
access and disk space. Review each model's license and access conditions before
use. Avoid sending sensitive prompts to a server you do not control.

llama.cpp
---------

The repository's ``Brewfile`` lists ``llama.cpp``. If it is not installed, run
``brew install llama.cpp``. Check the tools with ``llama-cli --help`` and
``llama-server --help``. The commands below use the Homebrew executables, not
Python bindings.

Generate one response using a small GGUF model:

.. code-block:: shell

   llama-cli -hf ggml-org/Qwen3.5-0.8B-GGUF \
     -p 'Say hello.' -n 128 --single-turn --simple-io

For an existing GGUF file, replace ``-hf ...`` with ``-m /path/to/model.gguf``.
The prompt and generated text appear in the terminal. The model may use some
of the token budget for reasoning. Adjust ``-n`` to change the generation
limit. See ``llama-cli --help`` for the options supported by the installed
version.

To expose an OpenAI-compatible API locally, start a server in one terminal:

.. code-block:: shell

   llama-server -hf ggml-org/Qwen3.5-0.8B-GGUF --host 127.0.0.1 --port 19931

Once it is ready, send a request from another terminal:

.. code-block:: shell

   curl -sS http://127.0.0.1:19931/v1/chat/completions \
     -H 'Content-Type: application/json' \
     -d '{"model":"local","messages":[{"role":"user","content":"Say hello."}],"max_tokens":128}'

Press Ctrl+C in the server terminal to stop it. Binding to ``127.0.0.1`` keeps
the listener local to the machine. Do not expose it to a network without
considering authentication and access controls.

MLX Python
----------

MLX is an array framework; ``mlx-lm`` adds language-model loading and text
generation. Neither is installed by the workshop's Pipenv configuration. Use a
separate virtual environment so the workshop's Python 3.15 environment remains
unchanged. The following uses Homebrew Python 3.14, which is installed on this
machine:

.. code-block:: shell

   python3.14 -m venv "$HOME/.venvs/workshop-mlx"
   "$HOME/.venvs/workshop-mlx/bin/python" -m pip install mlx-lm
   "$HOME/.venvs/workshop-mlx/bin/python" -c 'import mlx.core as mx; print(mx.array([1, 2, 3]) * 2)'

The last command should print an array containing ``2, 4, 6``. Installation
may require network access. The environment is independent of ``pipenv sync``;
its packages are not pinned by this repository.

Run a small MLX-compatible model:

.. code-block:: shell

   "$HOME/.venvs/workshop-mlx/bin/mlx_lm.generate" \
     --model mlx-community/SmolLM2-135M-Instruct-8bit \
     --prompt 'Say hello.' --max-tokens 20

To use the Python API, save this as ``example.py`` and run it with
``"$HOME/.venvs/workshop-mlx/bin/python" example.py``:

.. code-block:: python

   from mlx_lm import generate, load

   model, tokenizer = load("mlx-community/SmolLM2-135M-Instruct-8bit")
   messages = [{"role": "user", "content": "Say hello."}]
   prompt = tokenizer.apply_chat_template(
       messages, tokenize=False, add_generation_prompt=True
   )
   print(generate(model, tokenizer, prompt=prompt, max_tokens=20))

The model is downloaded on first use and cached. A GGUF file for llama.cpp is
not interchangeable with an MLX model; choose a model compatible with the
runtime. Larger models and longer contexts require more memory. If a model
cannot load or generation is slow, try a smaller quantized model or reduce its
context and output length.

Sources: `llama.cpp <https://github.com/ggml-org/llama.cpp>`_,
`MLX <https://github.com/ml-explore/mlx>`_, and
`MLX LM <https://github.com/ml-explore/mlx-lm>`_.
