import os
from ycmd import responses
from ycmd.completers.general_completer import GeneralCompleter
from ycmd.completers import completer_utils
from ycmd.utils import SplitLines
from third_party.tabnine import Tabnine


FILETYPE_TRIGGERS = {
    "c,\
  objc,objcpp,\
  ocaml,\
  cpp,cuda,objcpp,cs,\
  perl,\
  php,\
  d\
  elixir,\
  go,\
  gdscript,\
  groovy,\
  java,\
  javascript,\
  javascriptreact,\
  julia,\
  perl6,\
  python,\
  scala,\
  typescript,\
  typescriptreact,\
  vb,\
  ruby,rust,\
  lua,\
  erlang": list(
        "abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz(=[%/{+#.,\\<+-|&*=$#@!"
    )
}

CHAR_LIMIT = 100000
MAX_NUM_RESULTS = 5


class PartialDoc:
    def __init__(self, offset, text):
        self.offset = offset
        self.text = text

    def GetText(self):
        return self.text

    def GetOffset(self):
        return self.offset


class TabnineCompleter(GeneralCompleter):
    def __init__(self, user_options):
        super().__init__(user_options)
        self._settings_for_file = {}
        self._environment_for_file = {}
        self._environment_for_interpreter_path = {}
        self.completion_triggers = completer_utils.PreparedTriggers(
            default_triggers=FILETYPE_TRIGGERS
        )
        self._tabnine = Tabnine()

    def ComputeCandidatesInner(self, request_data):
        completions = []
        for file_name, file_data in request_data.get("file_data").items():
            before, after = self._GetBeforeAndAfter(request_data, file_name)
            region_includes_beginning = max(0, before.GetOffset() - CHAR_LIMIT) == 0
            region_includes_end = after.GetOffset() == len(file_data["contents"])

            request = {
                "before": before.GetText()[:CHAR_LIMIT],
                "after": after.GetText()[:CHAR_LIMIT],
                "filename": file_name,
                "max_num_results": MAX_NUM_RESULTS,
                "region_includes_beginning": region_includes_beginning,
                "region_includes_end": region_includes_end,
            }

            response = self._tabnine.auto_complete(request)

            if response is not None:
                completions += [
                    result.get("new_prefix") for result in response.get("results")
                ]

        return [
            responses.BuildCompletionData(
                insertion_text=completion, extra_menu_info="[⌬ tabnine]",
            )
            for completion in completions
        ]

    def ShouldUseNowInner(self, request_data):
        return True

    def _GetBeforeAndAfter(self, request_data, file_name):
        before_text = ""
        before_offset = 0

        line_num = request_data["line_num"]
        column_num = request_data["column_num"]
        lines = completer_utils.GetFileLines(request_data, file_name)

        # Before calculations
        for line in lines[: line_num - 1]:
            before_text += os.linesep + line
            before_offset += len(line) + 1

        last_line = lines[line_num - 1]

        before_text += last_line[: column_num - 1]
        before_offset += len(last_line[: column_num - 1])

        # After calculations
        after_offset = before_offset
        after_text = last_line[column_num:]

        after_offset += len(last_line[column_num:])
        for line in lines[line_num:]:
            after_text += os.linesep + line
            after_offset += len(line) + 1

        return (
            PartialDoc(before_offset, before_text),
            PartialDoc(after_offset, after_text),
        )

    # This is to disable caching Tabnine suggestions
    def _GetCandidatesFromSubclass(self, request_data):
        raw_completions = self.ComputeCandidatesInner(request_data)
        self._completions_cache.Update(request_data, raw_completions)
        return raw_completions

    def OpenTabnineHub(self):
        self._tabnine.configuration({})
