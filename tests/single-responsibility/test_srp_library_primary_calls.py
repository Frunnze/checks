"""
A library listed in an entity's catalogue reaches that entity through its
documented primary call: litellm.completion and acompletion,
google.generativeai GenerativeModel.generate_content, huggingface_hub
InferenceClient.chat_completion and text_generation (ai), and boto3
put_object, get_object and SQS send_message (network). Domain: those calls,
used inline or through a variable, in a unit that also writes a file.
Oracle: model (the unit reaches [entity, filesystem]).

Concrete inputs -> expected outputs:
- input:
      import litellm
      from pathlib import Path
      def answer(path):
          reply = litellm.completion(model='m', messages=[])
          Path(path).write_text(str(reply))
  output: <module>.answer -> ["ai", "filesystem"] (before the fix
  ["filesystem"], so the gate passed).
- input: `boto3.client('s3').put_object(Bucket='b', Key='k', Body=b'')`
  in place of the litellm call, with `import boto3`
  output: <module>.answer -> ["filesystem", "network"].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st
from srp_program_support import unit_entities

PRIMARY_CALLS = {
    "litellm.completion": (
        "ai",
        "import litellm",
        "litellm.completion(model='m', messages=[])",
    ),
    "litellm.acompletion": (
        "ai",
        "import litellm",
        "litellm.acompletion(model='m', messages=[])",
    ),
    "from litellm import completion": (
        "ai",
        "from litellm import completion",
        "completion(model='m', messages=[])",
    ),
    "GenerativeModel.generate_content": (
        "ai",
        "import google.generativeai as genai",
        "genai.GenerativeModel('gemini-pro').generate_content('hi')",
    ),
    "InferenceClient.chat_completion": (
        "ai",
        "from huggingface_hub import InferenceClient",
        "InferenceClient().chat_completion(messages=[])",
    ),
    "InferenceClient.text_generation": (
        "ai",
        "from huggingface_hub import InferenceClient",
        "InferenceClient().text_generation('hi')",
    ),
    "s3 put_object": (
        "network",
        "import boto3",
        "boto3.client('s3').put_object(Bucket='b', Key='k', Body=b'')",
    ),
    "s3 get_object": (
        "network",
        "import boto3",
        "boto3.client('s3').get_object(Bucket='b', Key='k')",
    ),
    "sqs send_message": (
        "network",
        "import boto3",
        "boto3.client('sqs').send_message(QueueUrl='u', MessageBody='m')",
    ),
}


@settings(max_examples=30, deadline=None)
@given(st.sampled_from(sorted(PRIMARY_CALLS)), st.booleans())
@example("litellm.completion", True)
def test_catalogued_library_primary_calls_reach_their_entity(
    name, through_variable
):
    entity, import_line, call = PRIMARY_CALLS[name]
    if through_variable:
        body = f"    reply = {call}\n"
    else:
        body = f"    print({call})\n    reply = None\n"
    source = (
        f"{import_line}\nfrom pathlib import Path\n\n\n"
        "def answer(path):\n"
        + body
        + "    Path(path).write_text(str(reply))\n"
    )

    entities = unit_entities(
        {"assistant.py": source}, "assistant.py", "callable", "<module>.answer"
    )

    assert entities == sorted({entity, "filesystem"})
