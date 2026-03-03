from flytekit import task, workflow
from flytekit.core.resources import Resources
import pathlib
import os
import tempfile
import re
import shutil

# Import the actual Python functions
from polus.images.formats.file_renaming.file_renaming import rename
from polus.images.formats.ome_converter.image_converter import batch_convert
from polus.images.regression.basic_flatfield_estimation import estimate
from polus.images.regression.basic_flatfield_estimation import utils as basic_utils
from polus.images.transforms.images.apply_flatfield import apply as apply_flatfield
from polus.images.segmentation.kaggle_nuclei_segmentation.segment import segment
import filepattern
import subprocess

# --- Resource config ---
CPU_REQUEST = "1"
CPU_LIMIT = "2"
MEM_REQUEST = "4Gi"
MEM_LIMIT = "8Gi"

# Default file extension for OME converter
OME_EXT = os.environ.get("POLUS_IMG_EXT", ".ome.tif")


def normalize_pattern(pattern: str) -> str:
    # Matches c{…:d} or c{…:dd} etc.
    return re.sub(r'([a-zA-Z])\{.*?(:d+)\}', lambda m: f"{m.group(1)}{{c{m.group(2)}}}", pattern)


def clean_dir(path: str) -> str:
    """Remove and recreate a directory."""
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)
    return path


def build_seg_pattern(base_pattern: str, channel_nuclei: int) -> str:
    """Build segmentation pattern by adding channel filter to base pattern.

    Args:
        base_pattern: Base file pattern (e.g., "img_{c:ddd}_{t:ddd}.ome.tif").
        channel_nuclei: Channel number for nuclei segmentation.

    Returns:
        Modified pattern with channel filter. The filepattern library will filter
        by the channel variable when used with FilePattern.
    """
    # The pattern itself doesn't change, but we'll filter by channel when using it
    # Return the same pattern - filtering will be done in the task
    return base_pattern

def run_docker(
    image: str,
    volumes: dict,
    command: list[str],
    shell: bool = False,
) -> None:
    cmd = ["docker", "run", "--rm"]
    for host, container in volumes.items():
        os.makedirs(host, exist_ok=True)
        cmd += ["-v", f"{host}:{container}"]
    cmd.append(image)
    cmd.extend(command)

    print(f"Running: {' '.join(cmd)}")

    if shell:
        cmd = " ".join(cmd)

    result = subprocess.run(cmd, check=False, capture_output=True, text=True, shell=shell)
   
    if result.stdout:
        print(f"STDOUT: {result.stdout}")
    if result.stderr:
        print(f"STDERR: {result.stderr}")
    
    print(f"Exit code: {result.returncode}")
    
    if result.returncode != 0:
        raise RuntimeError(f"Docker failed with exit code {result.returncode}\n{result.stderr}")

@task(
    requests=Resources(cpu=CPU_REQUEST, mem=MEM_REQUEST),
    limits=Resources(cpu=CPU_LIMIT, mem=MEM_LIMIT),
)
def file_renaming_local(
    input_dir: str,
    file_pattern: str,
    out_file_pattern: str,
) -> str:
    """Rename files according to the specified patterns.

    Args:
        input_dir: Input directory containing files to rename.
        file_pattern: Input file pattern to match files.
        out_file_pattern: Output file pattern for renamed files.

    Returns:
        String path to directory containing renamed files.
    """
    # Convert string to pathlib.Path and resolve to absolute path
    inp_dir_path = pathlib.Path(input_dir).resolve()

    # Create output directory using tempfile for better Flyte compatibility
    output_dir = pathlib.Path(tempfile.mkdtemp(prefix="renamed_"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Call the rename function
    rename(
        inp_dir=inp_dir_path,
        out_dir=output_dir,
        file_pattern=file_pattern,
        out_file_pattern=out_file_pattern,
    )

    # Return as string path
    return str(output_dir)


@task(
    requests=Resources(cpu=CPU_REQUEST, mem=MEM_REQUEST),
    limits=Resources(cpu=CPU_LIMIT, mem=MEM_LIMIT),
)
def ome_converter_local(
    input_dir: str,
    file_pattern: str,
    output_dir: str,
) -> str:
    """Convert images to OME format.

    Args:
        input_dir: Input directory containing images to convert.
        file_pattern: File pattern to match images.

    Returns:
        String path to directory containing converted OME images.
    """
    # Convert strings to pathlib.Path for batch_convert
    inp_dir_path = pathlib.Path(input_dir)
    out_dir_path = pathlib.Path(clean_dir(os.path.join(output_dir, "ome_converter")))
  
    # Call the batch_convert function
    batch_convert(
        inp_dir=inp_dir_path,
        out_dir=out_dir_path,
        file_pattern=file_pattern,
        file_extension=OME_EXT,
    )

    # Return as string path
    return str(out_dir_path)


@task(
    requests=Resources(cpu=CPU_REQUEST, mem=MEM_REQUEST),
    limits=Resources(cpu=CPU_LIMIT, mem=MEM_LIMIT),
)
def basic_flatfield_local(
    input_dir: str,
    file_pattern: str,
    group_by: str,
    output_dir: str,
) -> str:
    """Estimate flatfield using BaSiC algorithm.

    Args:
        input_dir: Input directory containing images.
        file_pattern: File pattern to match images.
        group_by: Variables to group images together for flatfield estimation.

    Returns:
        String path to directory containing flatfield images.
    """
    output_dir_str = clean_dir(os.path.join(output_dir, "basic_flatfield"))
    output_dir_path = pathlib.Path(output_dir_str)

    # Use filepattern to group images
    fp = filepattern.FilePattern(input_dir, file_pattern)
    extension = basic_utils.POLUS_IMG_EXT

    # Process each group
    for _, files in fp(group_by=list(group_by)):
        paths = [pathlib.Path(p) for _, [p] in files]
        # Estimate flatfield for this group
        estimate(paths, output_dir_path, get_darkfield=True, extension=extension)

    # Return as string path
    return str(output_dir_path)


@task(
    requests=Resources(cpu=CPU_REQUEST, mem=MEM_REQUEST),
    limits=Resources(cpu=CPU_LIMIT, mem=MEM_LIMIT),
)
def apply_flatfield_local(
    input_dir: str,
    file_pattern: str,
    ff_dir: str,
    output_dir: str,
) -> str:
    """Apply flatfield correction to images.

    Args:
        input_dir: Input directory containing images to correct.
        file_pattern: File pattern to match images.
        ff_dir: Directory containing flatfield images.
        group_by: Variables used for grouping in flatfield estimation (these will
            be excluded from flatfield file names).

    Returns:
        String path to directory containing corrected images.
    """
    ff_files = sorted(f for f in os.listdir(ff_dir) if "_flatfield" in f)
    df_files = sorted(f for f in os.listdir(ff_dir) if "_darkfield" in f)

    ff_pattern = filepattern.infer_pattern(files=ff_files)
    ff_pattern = normalize_pattern(ff_pattern)
    
    # Only set df_pattern if darkfield files actually exist
    # Otherwise set to None so df_fp will be None in apply_flatfield

    df_pattern = filepattern.infer_pattern(files=df_files)
    df_pattern = normalize_pattern(df_pattern)


    output_dir = clean_dir(os.path.join(output_dir, "apply_flatfield"))


    # Apply flatfield correction
    # Convert to pathlib.Path for apply_flatfield
    img_dir_path = pathlib.Path(input_dir)
    ff_dir_path = pathlib.Path(ff_dir)
    out_dir_path = pathlib.Path(output_dir)
    
    apply_flatfield(
        img_dir=img_dir_path,
        img_pattern=file_pattern,
        ff_dir=ff_dir_path,
        ff_pattern=ff_pattern,
        df_pattern=df_pattern,
        out_dir=out_dir_path,
        # preview=False,
        # keep_orig_dtype=True,
    )

    # Return as string path
    return str(out_dir_path)


@task(
    requests=Resources(cpu=CPU_REQUEST, mem=MEM_REQUEST),
    limits=Resources(cpu=CPU_LIMIT, mem=MEM_LIMIT),
)
def kaggle_nuclei_segmentation_local(
    input_dir: str,
    file_pattern: str,
    channel_nuclei: int,
    output_dir: str,
) -> str:
    """Segment nuclei using Kaggle U-Net model.

    Args:
        input_dir: Input directory containing images to segment.
        file_pattern: File pattern to match images.
        channel_nuclei: Channel number to filter for nuclei.
        output_dir: Output directory for segmented images.

    Returns:
        String path to directory containing segmented images.
    """
    # Convert strings to pathlib.Path
    inp_dir_path = pathlib.Path(input_dir)
    out_dir_path = pathlib.Path(clean_dir(os.path.join(output_dir, "segmented")))

    # Use filepattern to get all matching files, filtered by channel
    fps = filepattern.FilePattern(str(inp_dir_path), file_pattern)
    
    # Filter by channel if pattern has 'c' variable
    files = []
    for file in fps():
        # file is a tuple: (variables_dict, [file_path])
        file_vars = file[0]  # Variables dict
        if 'c' in file_vars and file_vars['c'] == channel_nuclei:
            files.append(str(file[1][0]))
        elif 'c' not in file_vars:
            # If no channel variable, include all files
            files.append(str(file[1][0]))

    # Process in batches (BATCH_SIZE = 20 from the tool)
    BATCH_SIZE = 20
    for ind in range(0, len(files), BATCH_SIZE):
        batch = ",".join(files[ind : min([ind + BATCH_SIZE, len(files)])])
        segment(batch, out_dir_path)

    # Return as string path
    return str(out_dir_path)


@task(
    requests=Resources(cpu=CPU_REQUEST, mem=MEM_REQUEST),
    limits=Resources(cpu=CPU_LIMIT, mem=MEM_LIMIT),
)
def ftl_label_local(
    input_dir: str,
    output_dir: str,
    connectivity: int = 1,
    binarization_threshold: float = 0.5,
) -> str:
    """Label connected components in binary images using FTL algorithm.

    Args:
        input_dir: Input directory containing binary images.
        output_dir: Output directory for labeled images.
        connectivity: Connectivity kind (must be <= number of dimensions). Default: 1.
        binarization_threshold: Threshold value for binarization. Default: 0.5.
            Note: The FTL label plugin doesn't support binarization threshold directly,
            so images should be pre-binarized before calling this function.

    Returns:
        String path to directory containing labeled images.
    """
    out_path = clean_dir(os.path.join(output_dir, "labeled")) 
    FTL_LABEL_IMAGE = "polusai/ftl-label-plugin:0.3.12-dev5"
    FTL_LABEL_COMMAND = [
        "--inpDir", input_dir,
        "--connectivity", str(connectivity),
        "--binarizationThreshold", str(binarization_threshold),
        "--outDir", out_path,
    ]
    run_docker(image=FTL_LABEL_IMAGE, volumes={input_dir: "/inputs", out_path: "/outputs"}, command=FTL_LABEL_COMMAND, shell=False)

    output_files = os.listdir(out_path)
    print(f"DEBUG labeled output: {output_files}")
    if not output_files:
        raise RuntimeError("FTL label produced no output files!")

    return str(out_path)

# Workflow
@workflow
def cellpainting_featureforge(
    input_dir: str,
    output_dir: str,
    filepattern: str,
    outfilepattern: str,
    group_by: str,
    channel_nuclei: int,
    features: str,
    file_extension: str,
) -> str:
    """Complete cell painting workflow with feature extraction.

    Args:
        input_dir: Input directory containing files.
        filepattern: Input file pattern to match files.
        outfilepattern: Output file pattern for renamed files.
        group_by: Variables to group images for flatfield estimation.
        channel_nuclei: Channel number for nuclei segmentation.
        features: Features to extract (not used in current implementation).
        file_extension: File extension for output files.

    Returns:
        String path to directory containing final processed images.
    """


    # Step 1: Rename files
    renamed = file_renaming_local(
        input_dir=input_dir,
        file_pattern=filepattern,
        out_file_pattern=outfilepattern,
    )

    # Step 2: Convert to OME format
    converted = ome_converter_local(
        input_dir=renamed,
        file_pattern=outfilepattern,
        output_dir=output_dir,
    )

    # # Step 3: Estimate flatfield
    basic_flatfield = basic_flatfield_local(
        input_dir=converted,
        file_pattern=outfilepattern,
        group_by=group_by,
        output_dir=output_dir,
    )

    # Step 4: Apply flatfield correction
    apply_flatfield = apply_flatfield_local(
        input_dir=converted,
        file_pattern=outfilepattern,
        ff_dir=basic_flatfield,
        output_dir=output_dir,
    )

    # # Step 5: Segment nuclei (filtering by channel happens inside the task)
    segmented = kaggle_nuclei_segmentation_local(
        input_dir=apply_flatfield,
        file_pattern=outfilepattern,
        channel_nuclei=channel_nuclei,
        output_dir=output_dir,
    )


    # output_dir = "./output"
    # segmented = "./output/segmented"
    # Step 6: Label connected components
    labeled = ftl_label_local(
        input_dir=segmented,
        output_dir=output_dir,
        connectivity=1,
        binarization_threshold=0.5,
    )

    # return labeled

    return "The workflow has completed successfully."