import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from pcpp.pcmd import CmdPreprocessor


def get_vitis_hls_dist_path() -> Path:
    vitis_hls_bin_path_str = shutil.which("vitis_hls")
    if vitis_hls_bin_path_str is None:
        raise RuntimeError("vitis_hls not found in PATH")
    vitis_hls_dist_path = Path(vitis_hls_bin_path_str).parent.parent
    return vitis_hls_dist_path


# def get_vitis_hls_clang_pp_path() -> Path:
#     vitis_hls_dist_path = get_vitis_hls_dist_path()
#     vitis_hls_clang_pp_path = (
#         vitis_hls_dist_path / "lnx64" / "tools" / "clang-3.9" / "bin" / "clang++"
#     )
#     if not vitis_hls_clang_pp_path.exists():
#         raise RuntimeError(
#             f"Could not find vitis_hls clang++ bin at {vitis_hls_clang_pp_path}"
#         )
#     return vitis_hls_clang_pp_path


def get_vitis_hls_clang_format_path() -> Path:
    vitis_hls_dist_path = get_vitis_hls_dist_path()
    vitis_hls_clang_format_path = (
        vitis_hls_dist_path / "lnx64" / "tools" / "clang-3.9" / "bin" / "clang-format"
    )
    if not vitis_hls_clang_format_path.exists():
        raise RuntimeError(
            f"Could not find vitis_hls clang-format bin at {vitis_hls_clang_format_path}"
        )
    return vitis_hls_clang_format_path


# def get_vitis_hls_include_dir() -> Path:
#     vitis_hls_dist_path = get_vitis_hls_dist_path()
#     vitis_hls_include_dir = (
#         vitis_hls_dist_path / "lnx64" / "tools" / "clang-3.9" / "include"
#     )
#     if not vitis_hls_include_dir.exists():
#         raise RuntimeError(
#             f"Could not find vitis_hls include dir at {vitis_hls_include_dir}"
#         )
#     return vitis_hls_include_dir


class SuppressOutput:
    def __enter__(self):
        # Save the current stdout and stderr
        self.save_stdout = sys.stdout
        self.save_stderr = sys.stderr

        # Redirect stdout and stderr to devnull
        self.devnull = open(os.devnull, "w")
        sys.stdout = self.devnull
        sys.stderr = self.devnull

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore stdout and stderr
        sys.stdout = self.save_stdout
        sys.stderr = self.save_stderr

        # Close the devnull file
        self.devnull.close()

        # Handle any exception that occurred in the block
        if exc_type is not None:
            print(f"Exception occurred: {exc_type}, {exc_val}")


def process_fp_kernel(kernel_dir: Path):
    kernel_name = kernel_dir.name
    kernel_c = kernel_dir / f"{kernel_name}.c"
    kernel_c_pp = kernel_dir / f"{kernel_name}_pp.c"

    fake_argv = [
        sys.argv[0],
        "-o",
        str(kernel_c_pp),
        "-I",
        str(kernel_dir),
        "--passthru-unfound-includes",
        str(kernel_c),
    ]

    preprocessor = CmdPreprocessor(fake_argv)
    with SuppressOutput():
        CmdPreprocessor(fake_argv)

    # remove any lines that start with #line and replace with \n
    txt = kernel_c_pp.read_text()
    txt = "\n".join(
        map(lambda x: x if not x.startswith("#line") else "\n", txt.split("\n"))
    )
    kernel_c_pp.write_text(txt)

    clang_format_path = get_vitis_hls_clang_format_path()
    # tab size if 4 spaces
    # clang_format_cmd = [str(clang_format_path), "-i", str(kernel_c_pp.name)]
    # print(clang_format_cmd)
    clang_format_cmd = [
        str(clang_format_path),
        # -style="{IndentWidth: 4}"
        "-style={BasedOnStyle: LLVM, IndentWidth: 4}",
        "-i",
        str(kernel_c_pp.name),
    ]
    p = subprocess.run(clang_format_cmd, cwd=kernel_dir, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr)
        raise RuntimeError(f"clang-format failed with return code {p.returncode}")


def main(args):
    n_jobs: int = args.jobs

    benchmark_distribution_fp: Path = args.benchmark_distribution
    output_dir: Path = args.output_directory
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file: Path = args.output_file

    # vitis_hls_include_dir = get_vitis_hls_include_dir()
    # vitis_clang_pp_bin_path = get_vitis_hls_clang_pp_path()

    if not benchmark_distribution_fp.exists():
        raise FileNotFoundError(
            "Benchmark distribution not found at {}".format(benchmark_distribution_fp)
        )

    is_zip = zipfile.is_zipfile(benchmark_distribution_fp)
    is_tar = tarfile.is_tarfile(benchmark_distribution_fp)

    if not is_zip and not is_tar:
        raise ValueError(
            "Benchmark distribution is not a zip or tar file: {}".format(
                benchmark_distribution_fp
            )
        )

    tmp_dir = output_dir / "tmp"
    new_benchmarks_dir = output_dir / "benchmarks"

    if is_zip:
        with zipfile.ZipFile(benchmark_distribution_fp, "r") as zip_ref:
            zip_ref.extractall(tmp_dir)
    if is_tar:
        raise NotImplementedError(
            "Tar file extraction not implemented for this benchmark distribution"
        )

    extracted_dir = next(tmp_dir.iterdir())
    print(extracted_dir)

    # for file in tmp_dir.glob(str(extracted_dir)):
    for file in tmp_dir.glob("**/*"):
        os.rename(file, tmp_dir / file.name)
    shutil.rmtree(extracted_dir)

    # source_benchmark_dirs = [tmp_dir / path for path in KERNEL_PATHS]
    # print(source_benchmark_dirs)

    FP_KERNELS = [
        "dfadd",
        "dfdiv",
        "dfmul",
        "dfsin",
    ]
    for kernel in FP_KERNELS:
        process_fp_kernel(tmp_dir / kernel)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "benchmark_distribution",
        type=Path,
        nargs="?",
        default=Path("./ferrandi-CHStone-main-557c623.zip"),
        help="Path to the input benchmark distribution",
    )
    parser.add_argument(
        "output_directory",
        type=Path,
        nargs="?",
        default=Path("./hls-chstone/"),
        help="Generated output directory with processed benchmarks",
    )
    parser.add_argument(
        "output_file",
        type=Path,
        nargs="?",
        default=Path("./hls-chstone.tar.gz"),
        help="Generated output tar.gz file with processed benchmarks",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        nargs="?",
        default=1,
        help="Number of jobs to run in parallel",
    )

    args = parser.parse_args()
    main(args)
