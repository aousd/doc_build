#! /usr/bin/env python3
import argparse
import inspect
import shutil
import subprocess
import sys
import platform
import os
import re
import time
from datetime import datetime
from typing import Dict

if sys.version_info < (3, 10):
    sys.exit("Python 3.10 or greater is required.")


class DocBuilder:
    def __init__(self):
        super().__init__()

    # MARK: Target Functions
    def build_docs(self, args):
        print(f"Building documentation in {args.output}...")
        if args.clean:
            self.clean_docs(args)

        pandoc = self.find_pandoc()

        os.makedirs(args.output, exist_ok=True)
        shutil.copytree(
            self.get_specification_root(),
            self.get_artifacts_dir(args),
            dirs_exist_ok=True,
        )
        combined = self.preprocess_build(args)

        spec = self.get_metadata_defaults_file()
        subtitle = self.get_subtitle(spec)

        # Set the cwd to the artifacts dir because its easier for some filters to work relatively to it
        os.chdir(self.get_artifacts_dir(args))
        shared_command = [
            pandoc,
            "--defaults",
            spec,
            combined,
            "--from=gfm+",
            "-F",
            self.get_filter("convert_mathblocks"),
            "-F",
            self.get_filter("bold_in_pre"),
            "-F",
            self.get_filter("resolve_sections"),
            "-V",
            f"date={datetime.today().strftime('%Y-%m-%d')}",
            "-V",
            f"subtitle={subtitle}",
            "-V",
            "geometry:margin=2.5cm",
            "-V",
            "linestretch=1.25",
            "-V",
            "fontsize=12pt",
            "-V",
            "mainfont=Georgia",
            "-V",
            f"AOUSD_ARTIFACTS_ROOT={self.get_artifacts_dir(args)}",
            "--toc=true",
            "--toc-depth",
            "4",
            "--standalone",
            "--number-sections=true",
            "--from=markdown-hard_line_breaks",
            "--pdf-engine=tectonic",
        ]

        if not args.no_draft:
            print("\tAdding Draft Watermark...")
            shared_command.extend(["-V", "draft=true"])

        pdf = None
        docx = None
        html = None

        filename = "aousd_core_spec"

        if not args.no_html:
            html = os.path.join(args.output, f"{filename}.html")
            html_template = os.path.join(
                self.get_scripts_root(), "template/default.html5"
            )
            print(f"\tBuilding HTML to {html}...")
            subprocess.check_call(
                shared_command
                + [
                    "-o",
                    html,
                    "--toc",
                    "--standalone",
                    "--embed-resources",
                    f"--template={html_template}",
                    "--mathml",
                ]
            )

        if not args.no_pdf:
            pdf = os.path.join(args.output, f"{filename}.pdf")
            latex_template = os.path.join(
                self.get_scripts_root(), "template/default.latex"
            )
            print(f"\tBuilding PDF to {pdf}...")
            process = subprocess.Popen(
                shared_command + ["-o", pdf, f"--template={latex_template}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            std_out, std_err = process.communicate()

            if std_err := std_err.decode("utf-8"):
                lines = std_err.splitlines()

                for line in lines:
                    # Spurious warning: https://github.com/tectonic-typesetting/tectonic/discussions/1192#discussioncomment-9463365
                    if line.startswith("warning: Trying to include PDF file with version "):
                        continue
                    # Can be safely ignored: https://www.overleaf.com/learn/how-to/Understanding_underfull_and_overfull_box_warnings
                    if line.startswith("warning: texput.tex:") and "Overfull " in line:
                        continue
                    # Can also be safely ignored
                    if line.startswith("warning: accessing absolute path "):
                        continue

                    print(line)

            if std_out := std_out.decode("utf-8"):
                print(std_out)

        if not args.no_docx:
            docx = os.path.join(args.output, f"{filename}.docx")
            print(f"\tBuilding DocX to {docx}...")
            subprocess.check_call(
                shared_command + ["-o", docx, "-F", self.get_filter("convert_svg")]
            )

        return pdf, docx, html

    def preprocess_build(self, args, substitutions=None):
        artifacts = self.get_artifacts_dir(args)
        print(f"\tBuilding Preprocessing artifacts in {artifacts}...")

        entry_point = self.get_entry_point(args)
        combined = self.get_combined_file_name(args)

        self.flatten(args, entry_point, combined, substitutions=substitutions)

        return combined

    def flatten(self, args, source, output, substitutions: Dict[str, str] = None):
        print(f"\tFlattening {source}...")
        substitutions = substitutions or {}
        artifacts = self.get_artifacts_dir(args)
        with open(source, "r") as source_file:
            lines = source_file.readlines()
            with open(output, "w") as out:
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

                        with open(path, "r") as section:
                            out.write(section.read())
                            out.write("\n\n")

                    else:
                        out.write(line)

    def clean_docs(self, args):
        if os.path.exists(args.output):
            shutil.rmtree(args.output)

    def run_linter(self, args):
        combined = self.get_combined_file_name(args)
        print(f"Linting {combined} ...")
        assert os.path.exists(combined), f"Could not find {combined}"

        pandoc = self.find_pandoc()

        linted = os.path.join(args.output, "linted.md")
        command = [
            pandoc,
            "-s",
            "-f",
            "markdown-smart",
            "--wrap=preserve",
            "-o",
            linted,
            combined,
        ]

        subprocess.check_call(command)
        print(f"\tLint output: {linted}")

    def export_git_archive(self, args):
        timestr = time.strftime("%Y%m%d-%H%M%S")
        filename = f"aousd_core_spec_{args.branch}_{timestr}.zip"
        filepath = os.path.join(args.output, filename)
        print(f"Exporting archive to {filepath}...")
        subprocess.check_call(
            ["git", "archive", "--format", "zip", "--output", filepath, args.branch]
        )
        return filepath

    def display_todos(self, args):
        print(f"Listing Todos under {args.output}...")
        # Configuration for exclusions
        EXCLUDE_DIRS = {"docs", ".git", ".idea"}
        EXCLUDE_FILES = {"Makefile"}
        EXCLUDE_PATHS = {"./filters/pegen", "./trash", "./build", "./tools"}
        TODO_PATTERN = "TODO"
        FIXME_PATTERN = "TODO"

        for dirpath, dirnames, filenames in os.walk(args.output):
            # Remove excluded directories from traversal
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

            for filename in filenames:
                filepath = os.path.join(dirpath, filename)

                # Skip excluded files and paths
                if filename in EXCLUDE_FILES or any(
                    filepath.startswith(ep) for ep in EXCLUDE_PATHS
                ):
                    continue

                # Check for 'TODO' in each file
                try:
                    with open(filepath, "r", encoding="utf-8") as file:
                        for lineno, line in enumerate(file, start=1):
                            if (TODO_PATTERN in line) or (FIXME_PATTERN in line):
                                relative_path = os.path.relpath(filepath, ".")
                                print(f"{relative_path}:{lineno}:{line.strip()}")
                except (UnicodeDecodeError, OSError):
                    # Skip files that can't be read
                    pass

    def build_index(self, args):
        print(f"Building index from {args.output}...")
        pandoc = self.find_pandoc()
        artifacts = self.get_artifacts_dir(args)
        source = os.path.join(artifacts, "usd_spec.md")
        output_md = os.path.join(artifacts, "index.md")
        output_tsv = os.path.join(args.output, "index.tsv")

        index_yaml = os.path.join(artifacts, "build_index.yaml")
        self.write_yaml(index_yaml, {"OUTPUT": output_tsv})

        command = [
            pandoc,
            source,
            "--metadata-file",
            index_yaml,
            "-F",
            self.get_filter("generate_index"),
            "-o",
            output_md,
        ]

        subprocess.check_call(command)

        return output_tsv

    def display_spellcheck_issues(self, args):
        combined = self.get_combined_file_name(args)
        print(f"Checking spellings in {combined}...")
        assert os.path.exists(combined), f"Could not find {combined}"

        fixed = os.path.join(args.output, "spellings_corrected.md")
        command = [self.find_pandoc(), "-F", self.get_filter("spellcheck"), "-o", fixed]

        subprocess.check_call(command)

        return fixed

    def display_style_issues(self, args):
        combined = self.get_combined_file_name(args)
        print(f"Checking styles in {combined}...")
        assert os.path.exists(combined), f"Could not find {combined}"

        print(
            "Legend:"
            "\n\t\033[91mWeasel Words\033[0m"
            "\n\t\033[95mIrregulars\033[0m"
            "\n\t\033[93mDuplicates\033[0m"
            "\n\n"
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
                    print(f"{lineno}: {highlighted_line.strip()}")
                if irregular_pattern.search(line):
                    highlighted_line = irregular_pattern.sub(
                        lambda m: f"\033[95m{m.group(0)}\033[0m", line
                    )
                    print(f"{lineno}: {highlighted_line.strip()}")

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
                        print(f"{lineno} \n\t\033[93m{word}\033[0m")

                    # Mark this as the last word
                    last_word = word

    # MARK: Path constants

    def _get_class_file(self):
        return inspect.getfile(self.__class__)

    def get_scripts_root(self):
        return os.path.dirname(os.path.abspath(__file__))

    def get_repo_root(self):
        """Assumes that the repo root is two up from this root"""
        return os.path.dirname(os.path.dirname(self._get_class_file()))

    def get_specification_root(self):
        return os.path.join(self.get_repo_root(), "specification")

    def get_default_build_output_root(self):
        return os.getenv("AOUSD_BUILD") or os.path.join(self.get_repo_root(), "build")

    def get_artifacts_dir(self, args):
        if isinstance(args, str):
            output = args
        else:
            output = args.output
        return os.path.join(output, "artifacts")

    def get_entry_point(self, args):
        return os.path.join(self.get_artifacts_dir(args), "README.md")

    # MARK: Utility Functions

    def get_subtitle(self, defaults_file_path):
        with open(defaults_file_path, "r") as f:
            import yaml

            spec_data = yaml.load(f, Loader=yaml.SafeLoader)
            commit = (
                subprocess.check_output(
                    ["git", "rev-parse", "--short", "HEAD"], cwd=self.get_repo_root()
                )
                .decode("utf-8")
                .strip()
            )
            subtitle = f"v{spec_data['metadata']['version']} ({commit})"
        return subtitle

    def get_combined_file_name(self, args):
        artifacts = self.get_artifacts_dir(args)
        return os.path.join(artifacts, "usd_spec.md")

    def find_pandoc(self):
        pandoc = shutil.which("pandoc")
        if not pandoc:
            sys.exit("Please install Pandoc")
        return pandoc

    def get_filter(self, name):
        path = os.path.join(self.get_scripts_root(), "filters", f"filter_{name}.py")
        assert os.path.exists(path), f"Could not find {path}"
        return path

    def write_yaml(self, output, data):
        try:
            import yaml
        except ImportError:
            sys.exit("Please install the PyYAML package: pip install PyYAML.")

        with open(output, "w") as f:
            yaml.dump(data, f)

    def should_process(self, document, args):
        if args.exclude and document in args.exclude:
            return False
        if args.only and document not in args.only:
            return False

        return True

    def get_metadata_defaults_file(self):
        this_path = inspect.getfile(self.__class__)
        this_dir = os.path.dirname(this_path)
        this_spec = os.path.join(this_dir, "defaults.yaml")
        if os.path.exists(this_spec):
            return this_spec

        return os.path.join(self.get_scripts_root(), "defaults.yaml")

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
        export_parser.set_defaults(func=self.export_git_archive)
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


if __name__ == "__main__":
    DocBuilder().process_argparser()
