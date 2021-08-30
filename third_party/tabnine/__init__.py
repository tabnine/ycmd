import json
import os
import platform
import subprocess
import stat
import threading
import zipfile

from urllib.request import urlopen, urlretrieve
from urllib.error import HTTPError

_TABNINE_SERVER_URL = "https://update.tabnine.com/bundles"
_TABNINE_EXECUTABLE = "TabNine"
_VERSION = "0.0.1"


class TabnineDownloader(threading.Thread):
    def __init__(self, download_url, output_dir, tabnine):
        threading.Thread.__init__(self)
        self.download_url = download_url
        self.output_dir = output_dir
        self.tabnine = tabnine

    def run(self):
        try:
            if not os.path.isdir(self.output_dir):
                os.makedirs(self.output_dir)
            zip_path, _ = urlretrieve(self.download_url)
            with zipfile.ZipFile(zip_path, "r") as zf:
                for filename in zf.namelist():
                    zf.extract(filename, self.output_dir)
                    target = os.path.join(self.output_dir, filename)
                    add_execute_permission(target)
        except Exception as e:
            pass


class Tabnine(object):
    def __init__(self):
        self._proc = None
        self._response = None
        self._install_dir = os.path.dirname(os.path.realpath(__file__))
        self._binary_dir = os.path.join(self._install_dir, "binaries")
        self.download_if_needed()

    def configuration(self, data):
        return self.request({"Configuration": data})

    def auto_complete(self, data):
        return self.request({"Autocomplete": data})

    def request(self, data):
        proc = self._get_running_tabnine()
        if proc is None:
            return
        try:
            request_json = json.dumps({"request": data, "version": "3.5.34"})
            proc.stdin.write((request_json + "\n").encode("utf8"))
            proc.stdin.flush()
        except BrokenPipeError:
            self._restart()
            return None

        output = proc.stdout.readline().decode("utf8")
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None

    def _restart(self):
        if self._proc is not None:
            self._proc.terminate()
            self._proc = None
        path = get_tabnine_path(self._binary_dir)
        if path is None:
            return
        self._proc = subprocess.Popen(
            [
                path,
                "--client",
                "vim-ycmd",
                "--log-file-path",
                os.path.join(self._install_dir, "tabnine.log"),
                "--client-metadata",
                "pluginVersion={}".format(_VERSION),
                "clientVersion={}".format(_VERSION),  # TODO add real version
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def _get_running_tabnine(self):
        if self._proc is None:
            self._restart()
        if self._proc is not None and self._proc.poll():
            self._restart()
        return self._proc

    def download_if_needed(self):
        if os.path.isdir(self._binary_dir):
            tabnine_path = get_tabnine_path(self._binary_dir)
            if tabnine_path is not None:
                add_execute_permission(tabnine_path)
                return
        self._download()

    def _download(self):
        version = get_tabnine_version()
        distro = get_distribution_name()
        download_url = "{}/{}/{}/{}.zip".format(
            _TABNINE_SERVER_URL, version, distro, _TABNINE_EXECUTABLE
        )
        output_dir = os.path.join(self._binary_dir, version, distro)
        TabnineDownloader(download_url, output_dir, self).start()


def get_tabnine_version():
    version_url = "{}/{}".format(_TABNINE_SERVER_URL, "version")

    try:
        return urlopen(version_url).read().decode("UTF-8").strip()
    except HTTPError:
        return None


arch_translations = {
    "arm64": "aarch64",
    "AMD64": "x86_64",
}


def get_distribution_name():
    sysinfo = platform.uname()
    sys_architecture = sysinfo.machine

    if sys_architecture in arch_translations:
        sys_architecture = arch_translations[sys_architecture]

    if sysinfo.system == "Windows":
        sys_platform = "pc-windows-gnu"

    elif sysinfo.system == "Darwin":
        sys_platform = "apple-darwin"

    elif sysinfo.system == "Linux":
        sys_platform = "unknown-linux-musl"

    elif sysinfo.system == "FreeBSD":
        sys_platform = "unknown-freebsd"

    else:
        raise RuntimeError(
            "Platform was not recognized as any of " "Windows, macOS, Linux, FreeBSD"
        )

    return "{}-{}".format(sys_architecture, sys_platform)


def get_tabnine_path(binary_dir):
    distro = get_distribution_name()
    versions = os.listdir(binary_dir)
    versions.sort(key=parse_semver, reverse=True)
    for version in versions:
        path = os.path.join(
            binary_dir, version, distro, executable_name(_TABNINE_EXECUTABLE)
        )
        if os.path.isfile(path):
            return path


def parse_semver(s):
    try:
        return [int(x) for x in s.split(".")]
    except ValueError:
        return []


def add_execute_permission(path):
    st = os.stat(path)
    new_mode = st.st_mode | stat.S_IEXEC
    if new_mode != st.st_mode:
        os.chmod(path, new_mode)


def executable_name(name):
    if platform.system() == "Windows":
        return name + ".exe"
    else:
        return name
