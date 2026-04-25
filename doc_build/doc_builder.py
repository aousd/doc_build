#! /usr/bin/env python3
import argparse
import json
import contextlib
import inspect
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import types
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Union

from doc_build.ast_diff import diff_ast_files
from doc_build.diff_colors import (
    DIFF_SECTION_DEL_PALE_RED,
    DIFF_SECTION_INS_PALE_GREEN,
    DIFF_WORD_DEL_RED,
    DIFF_WORD_INS_GREEN,
)
from doc_build.utils import git as git_utils

try:
    import yaml
except ImportError:
    sys.exit("Please install the PyYAML package: pip install PyYAML.")

if sys.version_info < (3, 10):
    sys.exit("Python 3.10 or greater is required.")


# The output format for the published aousd_core_spec.md file.  We want it to be
# in a widely / known format, that still has a decent set of extensions to
# enable features used in these documents, so we again go with `gfm`.
MARKDOWN_OUTPUT_FORMAT = "gfm"

MARKDOWN_FORMAT = "markdown-hard_line_breaks"
COMBINED_SPEC_BASENAME = "combined_spec"
COMBINED_SPEC_FILENAME = f"{COMBINED_SPEC_BASENAME}.md"

DIFF_BEFORE_FILENAME_TEMPLATE = "{base}.before_{from_short}"
DIFF_AFTER_FILENAME_TEMPLATE = "{base}.after_{to_short}"
DIFF_DIFF_FILENAME_TEMPLATE = "{base}.diff_{from_short}_to_{to_short}"

class _ZeroToTwoArgsAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if values is not None and hasattr(values, "__len__") and len(values) > 2:
            raise argparse.ArgumentError(
                self, f"{option_string} takes 0 to 2 arguments, got {len(values)}"
            )
        setattr(namespace, self.dest, values)


class Logger:

    def __log(self, msg, *args, **kwargs):
        print(msg, *args, **kwargs)
        return self

    def __call__(self, msg, *args, **kwargs):
        return self.__log(msg, *args, **kwargs)

    def __lshift__(self, msg):
        return self.__log(msg)


log = Logger()


class ExecCommand:
    def __init__(self, binary_name):
        if binary := shutil.which(binary_name):
            self.binary = binary
        else:
            sys.exit(f"Please install {binary_name}")

    def __run(self, arguments, stderr_processor=None, *args, **kwargs):
        command = [self.binary] + arguments
        if stderr_processor:

            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, *args, **kwargs
            )
            std_out, std_err = process.communicate()

            if std_err := std_err.decode("utf-8"):
                stderr_processor(std_err)

            if std_out := std_out.decode("utf-8"):
                log(std_out)
        else:
            subprocess.check_call(command, *args, **kwargs)

        return self

    def __call__(self, arguments, *args, **kwargs):
        return self.__run(arguments, *args, **kwargs)

    def __lshift__(self, arguments):
        return self.__run(arguments)

    def get_output(self, arguments, *args, **kwargs):
        command = [self.binary] + arguments

        return subprocess.check_output(command, *args, **kwargs).decode("utf-8")


pandoc = ExecCommand("pandoc")
tectonic = ExecCommand("tectonic")
git = ExecCommand("git")


def _ensure_windows_wrapper_exe(capture_wrapper: Path, wrapper_exe: Path) -> None:
    """Build the tectonic.exe wrapper via PyInstaller if it does not exist or is stale.

    Rebuilds if wrapper_exe is older than capture_wrapper (the Python source).
    Uses `pixi exec pyinstaller` so PyInstaller need not be a permanent dependency.
    """
    if wrapper_exe.exists() and wrapper_exe.stat().st_mtime >= capture_wrapper.stat().st_mtime:
        return

    import tempfile

    log("Building tectonic.exe wrapper via PyInstaller (one-time setup)...")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                "pixi",
                "exec",
                "pyinstaller",
                "--onefile",
                "--name",
                "tectonic",
                "--distpath",
                str(wrapper_exe.parent),
                "--workpath",
                tmp,
                "--specpath",
                tmp,
                "--noconfirm",
                str(capture_wrapper),
            ],
            check=True,
        )


def _call_wrapped_tectonic(
    pandoc_cmd: list,
    capture_wrapper: Path,
    real_tectonic: str,
    base_env: dict,
    stderr_processor,
    tex_file: Path,
    media_dir: Path,
) -> None:
    """Run pandoc with the tectonic capture wrapper active.

    Constructs the capture environment (TEX_CAPTURE_PATH, TEX_MEDIA_DIR,
    REAL_TECTONIC_PATH) and invokes pandoc.

    On Unix, injects the wrapper directory at the front of PATH so pandoc finds
    our shebang wrapper before the real tectonic.

    On Windows, pandoc ignores PATH and uses the tectonic that ships in the
    same pixi environment directory.  The real tectonic.exe must be inside the
    pixi project (i.e. pixi-managed); we temporarily rename it and drop the
    pre-built wrapper exe in its place, restoring everything via try/finally.
    Raises RuntimeError if the real tectonic is outside the pixi project.
    """
    capture_env = {
        **base_env,
        "TEX_CAPTURE_PATH": str(tex_file),
        "TEX_MEDIA_DIR": str(media_dir),
    }

    if sys.platform != "win32":
        run_env = {
            **capture_env,
            "REAL_TECTONIC_PATH": real_tectonic,
            "PATH": f"{capture_wrapper.parent}{os.pathsep}{capture_env.get('PATH', '')}",
        }
        pandoc(pandoc_cmd, stderr_processor=stderr_processor, env=run_env)
        return

    # Windows: pandoc finds tectonic via its own install directory, not PATH.
    # Resolve both paths before comparing to normalize mixed slashes and case.
    # capture_wrapper is <scripts_root>/tools/tectonic; project root is two levels up.
    pixi_project_root = capture_wrapper.parent.parent.parent.resolve()
    real_path = Path(real_tectonic).resolve()
    try:
        real_path.relative_to(pixi_project_root)
    except ValueError:
        raise RuntimeError(
            f"tectonic binary is outside the pixi project:\n"
            f"  tectonic: {real_path}\n"
            f"  project:  {pixi_project_root}\n"
            "Cannot safely intercept it on Windows."
        )

    wrapper_exe = capture_wrapper.parent / "tectonic.exe"
    _ensure_windows_wrapper_exe(capture_wrapper, wrapper_exe)
    renamed = real_path.with_name("tectonic.original.exe")
    real_path.rename(renamed)
    try:
        shutil.copy2(wrapper_exe, real_path)
        run_env = {**capture_env, "REAL_TECTONIC_PATH": str(renamed)}
        pandoc(pandoc_cmd, stderr_processor=stderr_processor, env=run_env)
    finally:
        real_path.unlink(missing_ok=True)
        renamed.rename(real_path)


class DocBuilder:
    def __init__(self, *, repo_root: Optional[Union[Path, str]] = None):
        super().__init__()
        if repo_root is not None:
            self._repo_root = Path(repo_root)
        else:
            self._repo_root = git_utils.repo_root(cwd=self._get_class_file().parent)

    # MARK: Target Functions
    def build_docs(self, args):
        log(f"Building documentation in {args.output}...")
        if args.clean:
            self.clean_docs(args)

        if args.diff is not None:
            if len(args.diff) == 0:
                latest_tag = git_utils.get_latest_semver_tag(self.get_repo_root())
                if latest_tag is None:
                    raise ValueError(
                        "--diff given with no arguments, but no semver tags (vX.Y.Z) "
                        "were found in the history of HEAD"
                    )
                args.diff = [latest_tag, "HEAD"]
            elif len(args.diff) == 1:
                args.diff.append("HEAD")
            elif len(args.diff) > 2:
                raise ValueError(
                    f"At most 2 arguments for --diff - got {len(args.diff)}"
                )
        args.output.mkdir(parents=True, exist_ok=True)

        if args.diff:
            from_ref, to_ref = args.diff[0], args.diff[1]
            before_md, after_md, diff_md, from_short, to_short = self.generate_combined_diff(
                args, from_ref, to_ref
            )
            base = self.get_file_base_name()
            from_pretty = git_utils.get_ref_pretty_str(from_ref, self.get_repo_root())
            to_pretty = git_utils.get_ref_pretty_str(to_ref, self.get_repo_root())

            # For an apples to apples comparison, we do a "final" render of the
            # full 3x3 matrix of:
            #  (before, after, diff) x (html, md, pdf)
            self._render_combined(
                args,
                combined=before_md,
                filename=DIFF_BEFORE_FILENAME_TEMPLATE.format(base=base, from_short=from_short),
                skip_docx=True,
                output_dir=args.output / "diff_from",
            )
            self._render_combined(
                args,
                combined=after_md,
                filename=DIFF_AFTER_FILENAME_TEMPLATE.format(base=base, to_short=to_short),
                skip_docx=True,
                output_dir=args.output / "diff_to",
            )
            return self._render_combined(
                args,
                combined=diff_md,
                filename=DIFF_DIFF_FILENAME_TEMPLATE.format(base=base, from_short=from_short, to_short=to_short),
                skip_docx=True,
                is_diff=True,
                output_dir=args.output / "diff",
                from_pretty=from_pretty,
                to_pretty=to_pretty,
            )
            # If everything succeeds, we should have an output tree like this
            # (not complete -other intermediate files will exist too...)
            # ├── build
            # │   ├── diff
            # │   │   ├── aousd_doc_build.diff_<fromhash>_to_<tohash>.html,
            # │   │   ├── aousd_doc_build.diff_<fromhash>_to_<tohash>.md
            # │   │   ├── aousd_doc_build.diff_<fromhash>_to_<tohash>.pdf
            # │   │   ├── images
            # │   │   │   ├── ...
            # │   ├── diff_from
            # │   │   ├── aousd_doc_build.before_<fromhash>.html
            # │   │   ├── aousd_doc_build.before_<fromhash>.md
            # │   │   ├── aousd_doc_build.before_<fromhash>.pdf
            # │   │   └── images
            # │   │       ├── ...
            # │   └── diff_to
            # │       ├── aousd_doc_build.after_<tohash>.html
            # │       ├── aousd_doc_build.after_<tohash>.md
            # │       ├── aousd_doc_build.after_<tohash>.pdf
            # │       └── images
            # │           ├── ...
        else:
            combined = self._setup_and_preprocess(args)
            return self._render_combined(args, combined, self.get_file_base_name())

    def _render_combined(
        self,
        args,
        combined,
        filename,
        *,
        skip_docx=False,
        is_diff=False,
        output_dir: Path | None = None,
        from_pretty: Optional[str] = None,
        to_pretty: Optional[str] = None,
    ):
        """Render HTML, PDF, Markdown, and optionally DOCX from a combined markdown file."""
        if output_dir is None:
            output_dir = args.output
        artifacts_dir = self.get_artifacts_dir(output_dir)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        spec = self.get_metadata_defaults_file()
        subtitle = self.get_subtitle(spec)

        front_page_dir = Path(__file__).resolve().parent / "front_page"
        fonts_dir = Path(__file__).resolve().parent / "fonts"

        # Use paths relative to artifacts_dir (the CWD when pandoc/tectonic
        # runs) so fontspec can locate fonts on any OS without drive-letter
        # issues in absolute paths.
        fontpath = Path(os.path.relpath(front_page_dir, artifacts_dir)).as_posix() + "/"
        dejavufontpath = Path(os.path.relpath(fonts_dir, artifacts_dir)).as_posix() + "/"

        doc_build_filters = []
        for doc_filter in self.get_doc_build_filters():
            doc_build_filters.extend(["-F", doc_filter])

        # Set the cwd to the artifacts dir because it's easier for some filters to work relatively to it.
        # contextlib.chdir restores the previous cwd on exit (even on exception), so on Windows the
        # process doesn't hold a handle to the directory and temp-dir cleanup succeeds.
        with contextlib.chdir(artifacts_dir):
            shared_command = [
                "--defaults",
                spec,
                combined,
                *doc_build_filters,
                "-V",
                f"date={datetime.today().strftime('%Y-%m-%d')}",
                "-V",
                f"fontpath={fontpath}",
                "-V",
                f"dejavufontpath={dejavufontpath}",
                "-V",
                f"subtitle={subtitle}",
                "-V",
                "geometry:margin=1in",
                # "geometry:margin=1cm",
                # "-V", "geometry:top=1cm", "-V", "geometry:bottom=2cm", "-V", "geometry:left=1cm", "-V", "geometry:right=1cm",
                "-V",
                # "linestretch=1.0",
                "linestretch=1.25",
                "-V",
                "fontsize=10pt",
                # "-V",
                # "mainfont=DejaVu Serif",
                # "-V",
                # "monofont=DejaVu Sans Mono",
                # "-V",
                # "monofontoptions=Scale=0.8",  # scale down a bit for better sizing of listings and PEG
                "-V",
                f"AOUSD_ARTIFACTS_ROOT={artifacts_dir}",
                "-V", f"diff-section-ins-pale-green={DIFF_SECTION_INS_PALE_GREEN}",
                "-V", f"diff-section-del-pale-red={DIFF_SECTION_DEL_PALE_RED}",
                "-V", f"diff-word-ins-green={DIFF_WORD_INS_GREEN}",
                "-V", f"diff-word-del-red={DIFF_WORD_DEL_RED}",
                "-V",
                "colorlinks=true",
                "-V",
                "linkcolor=OliveGreen",
                "-V",
                "toccolor=OliveGreen",
                "-V",
                "citecolor=OliveGreen",
                "-V",
                "urlcolor=blue",
                "--toc=true",
                "--toc-depth",
                "2",
                "--standalone",
                "--number-sections=true",
                "--from",
                MARKDOWN_FORMAT,
            ]

            if not args.no_draft:
                log("\tAdding Draft Watermark...")
                shared_command.extend(["-V", "draft=true"])

            if from_pretty is not None and to_pretty is not None:
                shared_command.extend([
                    "-M", f"diff-from-pretty={from_pretty}",
                    "-M", f"diff-to-pretty={to_pretty}",
                ])

            pdf = None
            docx = None
            html = None
            md = None

            if not args.no_md:
                md = output_dir / f"{filename}.md"
                md_template = self.get_scripts_root() / "template" / "default.md"
                bundle_images_filter = self.get_filter("bundle_images")
                bundle_images_args = [
                    "-M", f"AOUSD_OUTPUT_DIR={output_dir}",
                    "-M", f"AOUSD_IMAGES_ROOT={artifacts_dir}",
                    "-F", bundle_images_filter,
                ]
                log(f"\tBuilding Markdown to {md}...")
                pandoc(shared_command + bundle_images_args + ["-o", md, "--to", MARKDOWN_OUTPUT_FORMAT, f"--template={md_template}"])

            if not args.no_html:
                html = output_dir / f"{filename}.html"
                html_template = self.get_scripts_root() / "template" / "default.html5"
                log(f"\tBuilding HTML to {html}...")
                pandoc(
                    shared_command
                    + [
                        "-o",
                        html,
                        "--toc",
                        "--standalone",
                        "--mathml",
                        "--embed-resources",
                        f"--template={html_template}",
                    ]
                )

            if not args.no_pdf:
                pdf = output_dir / f"{filename}.pdf"
                template_dir = self.get_scripts_root() / "template"
                latex_template = template_dir / "default.latex"
                latex_diff_preamble = template_dir / "latex_diff_preamble.tex"

                # Fix the build timestamp so repeated runs produce bit-for-bit
                # identical PDFs (affects embedded dates and pdf-trailer-id).
                source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH") or str(int(time.time()))
                build_env = os.environ.copy()
                build_env["SOURCE_DATE_EPOCH"] = source_date_epoch

                def stderr_processor(std_err):
                    lines = std_err.splitlines()

                    for line in lines:
                        # Spurious warning: https://github.com/tectonic-typesetting/tectonic/discussions/1192#discussioncomment-9463365
                        if line.startswith(
                            "warning: Trying to include PDF file with version "
                        ):
                            continue
                        # Can be safely ignored: https://www.overleaf.com/learn/how-to/Understanding_underfull_and_overfull_box_warnings
                        if line.startswith("warning: texput.") and (
                            "Overfull " in line or "Underfull " in line
                        ):
                            continue
                        # Can also be safely ignored
                        if line.startswith("warning: accessing absolute path "):
                            continue

                        # Just reporting fluff
                        if line.startswith("warning: warnings were issued"):
                            continue

                        log(line, file=sys.stderr)

                pdf_extra = [f"--include-in-header={latex_diff_preamble}"] if is_diff else []
                latex_cmd_base = shared_command + [
                    f"--template={latex_template}",
                ] + pdf_extra

                if not getattr(args, "keep_pdf_latex", False):
                    # Standard path: pandoc pipes directly to tectonic via stdin.
                    log(f"\tBuilding PDF to {pdf}...")
                    pandoc(
                        latex_cmd_base + ["--pdf-engine=tectonic", "-o", pdf],
                        stderr_processor=stderr_processor,
                        env=build_env,
                    )
                else:
                    tex_file = output_dir / f"{filename}.tex"
                    recreate_script = output_dir / "recreate_pdf.py"

                    # A capture wrapper named "tectonic" intercepts the LaTeX pandoc
                    # pipes to tectonic, saves it to disk, then forwards to the real
                    # tectonic.  We use the bare engine name "--pdf-engine=tectonic" so
                    # pandoc applies its own SVG pre-conversion (only triggered by name,
                    # not a full path).  The wrapper is found first because its parent
                    # dir is prepended to PATH.
                    capture_wrapper = self.get_scripts_root() / "tools" / "tectonic"
                    # Ensure executable bit is set (can be lost when installed from git).
                    if sys.platform != "win32":
                        _mode = capture_wrapper.stat().st_mode
                        if not (_mode & stat.S_IXUSR):
                            capture_wrapper.chmod(_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

                    # casting to os-native path ensures consistent slashes - was getting paths like:
                    #    C:\\doc_build\\.pixi\\envs\\default\\Library/bin\\tectonic.EXE
                    tectonic_path = str(Path(tectonic.binary))

                    log(f"\tBuilding PDF to {pdf}...")
                    _call_wrapped_tectonic(
                        latex_cmd_base + ["--pdf-engine=tectonic", "-o", pdf],
                        capture_wrapper,
                        tectonic_path,
                        build_env,
                        stderr_processor,
                        tex_file=tex_file,
                        media_dir=output_dir / "images",
                    )

                    recreate_template = self.get_scripts_root() / "tools" / "recreate_pdf.py.template"
                    recreate_script.write_text(
                        recreate_template.read_text(encoding="utf-8").format(
                            source_date_epoch=source_date_epoch,
                            tectonic_path=tectonic_path,
                            tex_file_name=tex_file.name,
                            pdf_name=pdf.name,
                        ),
                        encoding="utf-8",
                    )
                    if sys.platform != "win32":
                        recreate_script.chmod(
                            recreate_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                        )

                    log(f"\tCaptured LaTeX: {tex_file}")
                    log(f"\tTo recreate PDF from .tex: {recreate_script}")

            if not args.no_docx and not skip_docx:
                docx = output_dir / f"{filename}.docx"
                log(f"\tBuilding DocX to {docx}...")
                pandoc(shared_command + ["-o", docx, "-F", self.get_filter("convert_svg")])

        return pdf, docx, html, md

    def get_doc_build_filters(self):
        """Return a list of paths to the filters the build_doc method runs in the order they must run"""
        return [
            self.get_filter("render_diff"),
            self.get_filter("convert_mathblocks"),
            self.get_filter("header6"),
            self.get_filter("resolve_sections"),
            self.get_filter("sections_new_page"),
            self.get_filter("smaller_listings"),
        ]

    def get_file_base_name(self):
        tokens = ["aousd"]
        remote_url = git_utils.get_remote_url(self.get_repo_root())
        if remote_url is not None:
            result = remote_url.split("/")[-1].replace(".git", "")
            tokens.extend([d for d in result.split("-") if d != "wg"])
        filename = "_".join(tokens)
        return filename

    def preprocess_build(self, args, substitutions=None):
        artifacts = self.get_artifacts_dir(args.output)
        log(f"\tBuilding Preprocessing artifacts in {artifacts}...")

        entry_point = self.get_entry_point(args)
        combined = self.get_combined_file_name(args.output)

        self.flatten(args, entry_point, combined, substitutions=substitutions)

        if args.no_draft:
            self.add_publish_copyright(combined)
        else:
            self.add_draft_copyright(combined)

        return combined

    def flatten(self, args, source, output, substitutions: Dict[str, str] = None):
        log(f"\tFlattening {source}...")
        substitutions = substitutions or {}
        artifacts = self.get_artifacts_dir(args.output)
        with open(source, "r", encoding="utf-8") as source_file:
            lines = source_file.readlines()
            with open(output, "w", encoding="utf-8") as out:
                for line in lines:
                    if res := re.search(r"\[(.*)]\((.*\.md)\)", line):
                        path = res.group(2)
                        tokens = path.split("/")
                        if len(tokens) > 1:
                            document = tokens[-2]
                        else:
                            document = os.path.splitext(tokens[-1])[0]
                        if not self.should_process(document, args):
                            continue

                        substituted_path = substitutions.get(path)
                        if substituted_path and os.path.exists(substituted_path):
                            path = substituted_path
                        else:
                            rel_path = os.path.join(os.path.dirname(source), path)
                            if os.path.exists(rel_path):
                                path = rel_path
                            else:
                                artifacts_path = os.path.join(artifacts, path)
                                if os.path.exists(artifacts_path):
                                    path = artifacts_path
                                else:
                                    raise IOError(f"Could not find {path}")
                        assert os.path.exists(path), f"Could not find {path}"

                        with open(path, "r", encoding="utf-8") as section:
                            out.write(section.read())
                            out.write("\n\n")

                    else:
                        out.write(line)

    def _setup_and_preprocess(self, args):
        """Copy specification into artifacts dir and run preprocess_build. Caller must ensure args.output exists."""
        shutil.copytree(
            self.get_specification_root(),
            self.get_artifacts_dir(args.output),
            dirs_exist_ok=True,
        )
        return self.preprocess_build(args)

    def _build_combined_for_ref(self, args, ref, worktree_path, output_subdir):
        """Build combined.md for a given ref using a temporary worktree. Removes worktree on exit."""
        worktree_path = Path(worktree_path)
        output_dir = Path(args.output) / output_subdir
        with git_utils.temp_worktree(self.get_repo_root(), ref, worktree_path):
            builder = self.__class__(repo_root=worktree_path)
            ref_args = types.SimpleNamespace(
                output=output_dir,
                no_draft=getattr(args, "no_draft", False),
                only=getattr(args, "only", []),
                exclude=getattr(args, "exclude", []),
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            return builder._setup_and_preprocess(ref_args)

    def generate_combined_diff(self, args, from_ref, to_ref):
        """Build combined diff markdown from two refs.

        Returns (before_md, after_md, diff_md, from_short, to_short).
        """
        from_short = git_utils.commit_hash(from_ref, self.get_repo_root(), short=True)
        to_short = git_utils.commit_hash(to_ref, self.get_repo_root(), short=True)
        diff_basename =DIFF_DIFF_FILENAME_TEMPLATE.format(
            base=COMBINED_SPEC_BASENAME,
            from_short=from_short,
            to_short=to_short
        )
        diff_dir = args.output / "diff"
        diff_dir.mkdir(parents=True, exist_ok=True)
        worktree_from = diff_dir / "wt_from"
        worktree_to = diff_dir / "wt_to"
        combined_from = self._build_combined_for_ref(
            args, from_ref, worktree_from, "diff_from"
        )
        combined_to = self._build_combined_for_ref(args, to_ref, worktree_to, "diff_to")
        ast_from = diff_dir / "ast_from.json"
        ast_to = diff_dir / "ast_to.json"

        # Convert markdown to JSON AST. Image paths are kept relative here so
        # that the LCS in ast_diff can match unchanged images between the two
        # versions (absolute paths would differ because the two worktrees are
        # in different directories). filter_diff_images resolves paths
        # relative to their respective artifacts dirs after diffing.
        inject_hash_filter = self.get_filter("inject_image_hash")
        for (md_input, ast_output) in [(combined_from, ast_from), (combined_to, ast_to)]:
            artifacts_dir = md_input.parent
            pandoc(
                [
                    md_input,
                    "-f",
                    MARKDOWN_FORMAT,
                    "-t",
                    "json",
                    "-o",
                    ast_output,
                    "-F",
                    inject_hash_filter,
                    "-M",
                    f"AOUSD_ARTIFACTS_DIR={artifacts_dir}",
                ]
            )

        diff_ast_path = diff_dir / f"{diff_basename}.json"
        diff_ast_files(str(ast_from), str(ast_to), str(diff_ast_path))

        # Copy images from
        #       build/diff_from/artifacts
        # and
        #       build/diff_to/artifacts
        # to
        #       build/diff_to/artifacts
        # ...so that bundle_images filter can find them.
        # Note that because this is before filter_bundle_images, we have to copy
        # the entire artifacts directory, not just the images subdirectory,
        # because images may live at any relative path.
        diff_artifacts = diff_dir / "artifacts"

        diff_from_artifacts = combined_from.parent
        shutil.copytree(diff_from_artifacts, diff_artifacts, dirs_exist_ok=True)

        # Just overwrite existing images, because for now we assume that same image path = same image
        diff_to_artifacts = combined_to.parent
        shutil.copytree(diff_to_artifacts, diff_artifacts, dirs_exist_ok=True)

        # Not strictly necessary (Pandoc can take JSON as input), but converting
        # to markdown unifies the pipeline with the non-diff path and eases debugging.
        combined_diff_md = diff_dir / f"{diff_basename}.md"
        pandoc(
            ["-f", "json", "-t", MARKDOWN_FORMAT, "-o", combined_diff_md, diff_ast_path]
        )
        return combined_from, combined_to, combined_diff_md, from_short, to_short

    def clean_docs(self, args):
        if args.output.exists():
            shutil.rmtree(args.output)

    def run_linter(self, args):
        combined = self.get_combined_file_name(args.output)
        log(f"Linting {combined} ...")
        assert combined.exists(), f"Could not find {combined}"

        linted = args.output / "linted.md"
        pandoc(
            ["-s", "-f", "markdown-smart", "--wrap=preserve", "-o", linted, combined]
        )

        log(f"\tLint output: {linted}")

    def _export_git_archive_from_args(self, args):
        return git_utils.export_git_archive(
            base_filename="aousd_core_spec",
            branch=args.branch,
            output=args.output,
        )

    def display_todos(self, args):
        log(f"Listing Todos under {args.output}...")
        # Configuration for exclusions
        EXCLUDE_DIRS = {"docs", ".git", ".idea"}
        EXCLUDE_FILES = {"Makefile"}
        EXCLUDE_PATHS = {"./filters/pegen", "./trash", "./build", "./tools"}
        TODO_PATTERN = "TODO"
        FIXME_PATTERN = "FIXME"

        for dirpath, dirnames, filenames in os.walk(args.output):
            # Remove excluded directories from traversal
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

            for filename in filenames:
                filepath = Path(dirpath) / filename

                # Skip excluded files and paths
                if filename in EXCLUDE_FILES or any(
                    filepath.resolve().as_posix().startswith(ep) for ep in EXCLUDE_PATHS
                ):
                    continue

                # Check for 'TODO' and 'FIXME' in each file
                try:
                    with filepath.open("r", encoding="utf-8") as file:
                        for lineno, line in enumerate(file, start=1):
                            if (TODO_PATTERN in line) or (FIXME_PATTERN in line):
                                relative_path = os.path.relpath(filepath, ".")
                                log(f"{relative_path}:{lineno}:{line.strip()}")
                except (UnicodeDecodeError, OSError):
                    # Skip files that can't be read
                    pass

    def build_index(self, args):
        log(f"Building index from {args.output}...")
        artifacts = self.get_artifacts_dir(args.output)
        source = artifacts / COMBINED_SPEC_FILENAME
        output_md = artifacts / "index.md"
        output_tsv = args.output / "index.tsv"

        index_yaml = artifacts / "build_index.yaml"
        self.write_yaml(index_yaml, {"OUTPUT": output_tsv.as_posix()})

        pandoc(
            [
                source,
                "--metadata-file",
                index_yaml,
                "-F",
                self.get_filter("generate_index"),
                "-o",
                output_md,
            ]
        )

        return output_tsv

    def display_spellcheck_issues(self, args):
        combined = self.get_combined_file_name(args.output)
        log(f"Checking spellings in {combined}...")
        assert combined.exists(), f"Could not find {combined}"

        fixed = args.output / "spellings_corrected.md"
        pandoc(["-F", self.get_filter("spellcheck"), combined, "-o", fixed])

        return fixed

    def display_style_issues(self, args):
        combined = self.get_combined_file_name(args.output)
        log(f"Checking styles in {combined}...")
        assert combined.exists(), f"Could not find {combined}"

        log(
            (
                "Legend:"
                "\n\t\033[91mWeasel Words\033[0m"
                "\n\t\033[95mIrregulars\033[0m"
                "\n\t\033[93mDuplicates\033[0m"
                "\n\n"
            )
        )

        # Define the default list of weasel words
        weasels = (
            "many|various|very|fairly|several|extremely|exceedingly|quite|remarkably|few|"
            "surprisingly|mostly|largely|huge|tiny|((are|is) a number)|excellent|"
            "interestingly|significantly|substantially|clearly|vast|relatively|completely"
        )
        weasel_pattern = re.compile(f"\\b({weasels})\\b", re.IGNORECASE)

        irregulars = (
            "awoken|been|born|beat|become|begun|bent|beset|bet|bid|bidden|bound|bitten|"
            "bled|blown|broken|bred|brought|broadcast|built|burnt|burst|bought|cast|"
            "caught|chosen|clung|come|cost|crept|cut|dealt|dug|dived|done|drawn|dreamt|"
            "driven|drunk|eaten|fallen|fed|felt|fought|found|fit|fled|flung|flown|"
            "forbidden|forgotten|foregone|forgiven|forsaken|frozen|gotten|given|gone|"
            "ground|grown|hung|heard|hidden|hit|held|hurt|kept|knelt|knit|known|laid|"
            "led|leapt|learnt|left|lent|let|lain|lighted|lost|made|meant|met|misspelt|"
            "mistaken|mown|overcome|overdone|overtaken|overthrown|paid|pled|proven|"
            "put|quit|read|rid|ridden|rung|risen|run|sawn|said|seen|sought|sold|sent|"
            "set|sewn|shaken|shaven|shorn|shed|shone|shod|shot|shown|shrunk|shut|sung|"
            "sunk|sat|slept|slain|slid|slung|slit|smitten|sown|spoken|sped|spent|spilt|"
            "spun|spit|split|spread|sprung|stood|stolen|stuck|stung|stunk|stridden|"
            "struck|strung|striven|sworn|swept|swollen|swum|swung|taken|taught|torn|"
            "told|thought|thrived|thrown|thrust|trodden|understood|upheld|upset|woken|"
            "worn|woven|wed|wept|wound|won|withheld|withstood|wrung|written"
        )
        irregular_pattern = re.compile(
            f"\\b(am|are|were|being|is|been|was|be)\\b[ ]*(\\w+ed|({irregulars}))\\b",
            re.IGNORECASE,
        )
        with open(combined, "r") as f:
            for lineno, line in enumerate(f.readlines(), start=1):
                if weasel_pattern.search(line):
                    highlighted_line = weasel_pattern.sub(
                        lambda m: f"\033[91m{m.group(0)}\033[0m", line
                    )
                    log(f"{lineno}: {highlighted_line.strip()}")
                if irregular_pattern.search(line):
                    highlighted_line = irregular_pattern.sub(
                        lambda m: f"\033[95m{m.group(0)}\033[0m", line
                    )
                    log(f"{lineno}: {highlighted_line.strip()}")

                last_word = ""
                words = re.split(r"(\W+)", line)

                for word in words:
                    # Skip spaces or empty strings
                    if not word.strip():
                        continue

                    # Skip punctuation
                    if re.match(r"^\W+$", word):
                        last_word = ""
                        continue

                    # Found a duplicate word?
                    if word.lower() == last_word.lower():
                        log(f"{lineno} \n\t\033[93m{word}\033[0m")

                    # Mark this as the last word
                    last_word = word

    # MARK: Path constants

    def _get_class_file(self) -> Path:
        return Path(inspect.getfile(self.__class__))

    def get_scripts_root(self) -> Path:
        return Path(__file__).resolve().parent

    def get_repo_root(self) -> Path:
        return self._repo_root

    def get_specification_root(self) -> Path:
        return self.get_repo_root() / "specification"

    def get_default_build_output_root(self) -> Path:
        return Path(os.getenv("AOUSD_BUILD", self.get_repo_root() / "build"))

    def get_artifacts_dir(self, output_path: Path) -> Path:
        if not isinstance(output_path, Path):
            if hasattr(output_path, "output"):
                output_path = output_path.output
            else:
                raise TypeError("Output Path should be a Path object")
        return output_path / "artifacts"

    def get_entry_point(self, args) -> Path:
        return self.get_artifacts_dir(args.output) / "README.md"

    # MARK: Utility Functions

    def get_subtitle(self, defaults_file_path: Path):
        with open(defaults_file_path, "r") as f:
            spec_data = yaml.load(f, Loader=yaml.SafeLoader)
            commit = git_utils.commit_hash("HEAD", self.get_repo_root(), short=True)
            subtitle = f"v{spec_data['metadata']['version']} ({commit})"
        return subtitle

    def get_combined_file_name(self, output_path: Path) -> Path:
        return self.get_artifacts_dir(output_path) / COMBINED_SPEC_FILENAME

    def get_filter(self, name: str) -> Path:
        path = self.get_scripts_root() / "filters" / f"filter_{name}.py"
        assert path.exists(), f"Could not find {path}"
        return path

    def write_yaml(self, output: Path, data: dict):
        if isinstance(output, str):
            output = Path(str)
        with output.open("w") as f:
            yaml.dump(data, f)

    def should_process(self, document, args):
        if args.exclude and document in args.exclude:
            return False
        if args.only and document not in args.only:
            return False

        return True

    def get_metadata_defaults_file(self) -> Path:
        this_path = self._get_class_file()
        this_spec = this_path.parent / "defaults.yaml"

        if this_spec.exists():
            return this_spec

        return self.get_scripts_root() / "defaults.yaml"

    # MARK: Argparser builds

    def process_argparser(self):
        parser = argparse.ArgumentParser(description="Documentation Build Utilities")
        self.construct_subparsers(parser)

        parser.add_argument(
            "-o",
            "--output",
            help="Output directory",
            default=self.get_default_build_output_root(),
        )

        args = parser.parse_args()
        args.func(args)

    def construct_subparsers(self, parser):
        subparsers = parser.add_subparsers(dest="command", required=True)
        self.make_build_parser(subparsers)
        self.make_clean_parser(subparsers)
        self.make_lint_parser(subparsers)
        self.make_export_parser(subparsers)
        self.make_todo_parser(subparsers)
        self.make_index_parser(subparsers)
        self.make_spellcheck_parser(subparsers)
        self.make_style_parser(subparsers)
        return subparsers

    def make_build_parser(self, subparsers):
        build_parser = subparsers.add_parser("build", help="Build documentation")

        build_parser.set_defaults(func=self.build_docs)

        build_parser.add_argument(
            "--no-html", help="Do not build HTML", action="store_true"
        )
        build_parser.add_argument(
            "--no-md", help="Do not build Markdown", action="store_true"
        )
        build_parser.add_argument(
            "--no-pdf", help="Do not build PDF", action="store_true"
        )
        build_parser.add_argument(
            "--no-docx", help="Do not build docx", action="store_true"
        )
        build_parser.add_argument(
            "--clean", help="Clean before building", action="store_true"
        )
        build_parser.add_argument(
            "--only", help="Only build certain docs", nargs="*", default=[]
        )
        build_parser.add_argument(
            "--exclude", help="Exclude docs", nargs="*", default=[]
        )
        build_parser.add_argument(
            "--no-draft", help="Do not add draft watermark", action="store_true"
        )
        build_parser.add_argument(
            "--keep-pdf-latex",
            help="Capture the intermediate LaTeX when building PDF, alongside a "
            "script to recreate the PDF from the .tex (implies tectonic wrapper)",
            action="store_true",
        )
        build_parser.add_argument(
            "--diff",
            nargs="*",
            metavar=("from_commit", "to_commit"),
            action=_ZeroToTwoArgsAction,
            help="Generate a document showing a diff between the given commits; "
            "if `to_commit` is not given, it defaults to HEAD; if no commits "
            "are given at all, uses the most recent semver release tag (vX.Y.Z) "
            "as `from_commit` and HEAD as `to_commit`. Commits may be git "
            "hashes, branch names, tags, or any other valid git reference "
            "understood by `git rev-parse`",
        )

        return build_parser

    def make_clean_parser(self, subparsers):
        clean_parser = subparsers.add_parser("clean", help="Clean documentation")
        clean_parser.set_defaults(func=self.clean_docs)
        return clean_parser

    def make_lint_parser(self, subparsers):
        lint_parser = subparsers.add_parser("lint", help="Lint documentation")
        lint_parser.set_defaults(func=self.run_linter)
        return lint_parser

    def make_export_parser(self, subparsers):
        export_parser = subparsers.add_parser("export", help="Export the git archive")
        export_parser.add_argument("-b", "--branch", default="main")
        export_parser.set_defaults(func=self._export_git_archive_from_args)
        return export_parser

    def make_todo_parser(self, subparsers):
        todo_parser = subparsers.add_parser(
            "todo", help="List all TODO and FIXME items"
        )
        todo_parser.set_defaults(func=self.display_todos)
        return todo_parser

    def make_index_parser(self, subparsers):
        index_parser = subparsers.add_parser("index", help="Build documentation index")
        index_parser.set_defaults(func=self.build_index)
        return index_parser

    def make_spellcheck_parser(self, subparsers):
        spellcheck_parser = subparsers.add_parser(
            "spellcheck", help="Spellcheck documentation"
        )
        spellcheck_parser.set_defaults(func=self.display_spellcheck_issues)
        return spellcheck_parser

    def make_style_parser(self, subparsers):
        style_parser = subparsers.add_parser(
            "stylecheck", help="Checks the style of the documentation"
        )
        style_parser.set_defaults(func=self.display_style_issues)
        return style_parser

    def add_publish_copyright(self, combined):
        intro_copyright = self.get_publish_intro_legalese()
        outro = self.get_publish_outro_legalese()
        content = self._read_file(combined)

        with open(combined, "w", encoding="utf-8") as f:
            f.write(intro_copyright)
            f.write(content)
            f.write(outro)

    def get_publish_intro_legalese(self):
        path = self.get_scripts_root() / "legal/publish_intro.md"
        return self._read_file(path)

    def get_publish_outro_legalese(self):
        path = self.get_scripts_root() / "legal/publish_outro.md"
        return self._read_file(path)

    def add_draft_copyright(self, combined):
        intro_copyright = self.get_intro_legalese()
        outro = self.get_outro_legalese()
        content = self._read_file(combined)

        with open(combined, "w", encoding="utf-8") as f:
            f.write(intro_copyright)
            f.write(content)
            f.write(outro)

    def get_intro_legalese(self):
        path = self.get_scripts_root() / "legal/draft_intro.md"
        return self._read_file(path)

    def get_outro_legalese(self):
        path = self.get_scripts_root() / "legal/draft_outro.md"
        return self._read_file(path)

    def _read_file(self, filename):
        if not filename.exists():
            raise IOError(f"Could not find {filename}")

        with open(filename, encoding="utf-8") as f:
            return f.read()


if __name__ == "__main__":
    DocBuilder().process_argparser()
