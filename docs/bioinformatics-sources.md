# Bioinformatics documentation capture candidates

Collected 2026-10-09. This is a scoped starting set for documentation reading and
shared page-text evidence, not a popularity ranking or an analysis-stack prescription.
Python's existing documentation fixture remains useful; these candidates extend
coverage beyond the Python language.

Official links below were located through public search or page retrieval.
**Live DOM capture and extraction validation are pending for every entry below.**
Search results/rendered retrieval text are not raw DOM fixtures. Proposed checks
do not assert that a site's current HTML uses any particular tags or selectors.

| Area | Technology and official entry point | Proposed evidence/check |
| --- | --- | --- |
| Statistical programming | [R manuals](https://cran.r-project.org/manuals.html) | Manual version, headings, function examples, HTML versus PDF links |
| Biological sequences in R | [Biostrings](https://bioconductor.org/packages/release/bioc/html/Biostrings.html) | Package metadata table and vignette/source links |
| RNA-seq statistics | [DESeq2 vignette](https://bioconductor.org/packages/release/bioc/vignettes/DESeq2/inst/doc/DESeq2.html) | Long article, R code/output, equations and internal anchors |
| Alignment and variant files | [SAMtools / HTSlib documentation](https://www.htslib.org/doc/) | CLI synopsis, option descriptions and preformatted spacing |
| Variant manipulation | [BCFtools how-to](https://samtools.github.io/bcftools/howtos/) | Command examples and links to individual operations |
| Genomic intervals | [BEDTools](https://bedtools.readthedocs.io/en/stable/index.html) | Coordinate examples, tables and linked subcommands |
| FASTA/FASTQ processing | [SeqKit](https://bioinf.shenwei.me/seqkit/) | CLI examples, multiline sequence data and navigation separation |
| File-format specifications | [HTS specifications](https://samtools.github.io/hts-specs/) | Specification/version links; identify PDF as PDF rather than parse as HTML |
| Workflow execution | [Nextflow](https://docs.seqera.io/nextflow/) | DSL code, configuration examples and navigation |
| Workflow execution | [Snakemake](https://snakemake.readthedocs.io/en/stable/) | Rules, indentation, configuration and version links |
| Reusable analysis pipelines | [nf-core introduction](https://nf-co.re/docs/usage/getting_started/introduction) | Pipeline/documentation links and cross-repository provenance |
| Quality-control reporting | [MultiQC pipeline integration](https://docs.seqera.io/multiqc/usage/pipelines) | Shell/YAML examples and workflow-specific sections |
| Software environments | [Bioconda](https://bioconda.github.io/) | Environment commands, warnings and collapsible explanatory text |
| HPC containers | [Apptainer user guide](https://apptainer.org/docs/user/latest/) | CLI flags, versioned documentation and installation links |
| Reference-data acquisition | [NCBI Datasets](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/) | CLI/data-model documentation and database identifier links |
| Genome annotation | [Ensembl training](https://training.ensembl.org/) | Training/documentation links and resource names |
| Browser-based analysis | [Galaxy data tutorial](https://training.galaxyproject.org/training-material/topics/galaxy-interface/tutorials/get-data/slides.html) | Slide navigation, instructional text and image alternatives |

The previous Nextflow entry point https://www.nextflow.io/docs/latest/ redirected
to https://docs.seqera.io/nextflow/ during retrieval. Capture receipts should retain
both requested and final URLs. Moving release/stable/latest pages are discovery
links, not immutable fixture versions.

## First small capture batch

Start with R, Biostrings, one SAMtools command page and one BEDTools command page:
these cover language manuals, package metadata, CLI help and coordinate examples.
Select concrete sections after examining each live DOM; do not guess selectors
from this catalogue. Next add a DESeq2 article section and a workflow code example.
Database search applications and large reports can follow once static text checks
are useful.

Use the existing capture example and page_text implementation described in
[dom-capture.md](dom-capture.md). Keep one bounded acquisition per selected page,
then replay the saved evidence locally for each reader. Record final URL, capture
time, encoding, selector, hashes, source/license and whether content is a real
fragment, a semantic projection or a modeled fixture. Avoid live-site calls in
ordinary regression tests.

Compare browser-visible text, static extraction and Markdown round-trip content
as separate results. Code whitespace, final newlines, coordinate conventions,
links and version labels must not disappear behind a broad normalization rule.
CSS-hidden permalinks can explain a difference but must remain visible in the
report. A capture success does not certify extraction or scientific correctness.

Browser launch/capture stays in browser-test-kit. GHI can consume explicit saved
HTML when useful for GitHub-linked investigation; this list does not add site
adapters, a second parser or browser dependencies to GHI. Shared fixtures should
be referenced at a fixed revision rather than independently recreated per repo.
