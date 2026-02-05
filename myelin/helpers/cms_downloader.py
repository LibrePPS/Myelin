#!/usr/bin/env python3
"""
CMS Downloader Module

This module provides the CMSDownloader class for downloading and organizing CMS software
for the CMS MSDRG Grouper and MCE Editor software, including the necessary dependencies like GFC, GRPC, and SLF4J.

Usage Example:
    # Basic usage - downloads all JARs to default directories
    downloader = CMSDownloader()
    success = downloader.build_jar_environment()

    # Custom directories
    downloader = CMSDownloader(
        jars_dir="/path/to/custom/jars",
        download_dir="/path/to/custom/downloads"
    )
    success = downloader.build_jar_environment(clean_existing=True)

    # Individual components
    downloader = CMSDownloader()
    downloader.download_web_pricers()  # Pricers go to jars/pricers/
    downloader.download_msdrg_files()
    downloader.process_gfc_jar()
"""

import glob
import logging
import os
import re
import shutil
import tempfile
import time
import zipfile
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


class CMSDownloader:
    """
    A class to download and manage CMS software JAR files and dependencies.
    """

    # Constants
    CMS_URL = "https://www.cms.gov/pricersourcecodesoftware"
    TARGET_HEADER = "Software (Executable JAR Files)"
    ZIP_PATH_PATTERN = "/files/zip/"
    MSDRG_URL = "https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/ms-drg-classifications-and-software"
    IOCE_URL = "https://www.cms.gov/medicare/coding-billing/outpatient-code-editor-oce/quarterly-release-files"
    JAVA_SOURCE_PATTERN = "java-source.zip"
    JAVA_STANDALONE_PATTERN = "java-standalone"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    GFC_JAR = "https://github.com/3mcloud/GFC-Grouper-Foundation-Classes/releases/download/v3.4.9/gfc-base-api-3.4.9.jar"
    GRPC_JAR1 = "https://repo1.maven.org/maven2/com/google/protobuf/protobuf-java/3.22.2/protobuf-java-3.22.2.jar"
    GRPC_JAR2 = "https://repo1.maven.org/maven2/com/google/protobuf/protobuf-java/3.21.7/protobuf-java-3.21.7.jar"
    SLF4J_JAR = "https://repo1.maven.org/maven2/org/slf4j/slf4j-simple/2.0.9/slf4j-simple-2.0.9.jar"
    SLF4J_JAR2 = (
        "https://repo1.maven.org/maven2/org/slf4j/slf4j-api/2.0.9/slf4j-api-2.0.9.jar"
    )
    HHAG_URL = "https://www.cms.gov/medicare/payment/prospective-payment-systems/home-health/home-health-grouper-software"
    CMG_URL = "https://www.cms.gov/medicare/payment/prospective-payment-systems/inpatient-rehabilitation/grouper-case-mix-group"
    REQUIRED_JARS = {
        "slf4j": ["slf4j-simple-2.0.9.jar", "slf4j-api-2.0.9.jar"],
        "gfc": ["gfc-base-api-3.4.9.jar"],
        "grpc": ["protobuf-java-3.22.2.jar", "protobuf-java-3.21.7.jar"],
        "msdrg": [
            r"msdrg-binary-access-[\d\.]+\.jar",
            r"msdrg-model-v2-[\d\.]+\.jar",
            r"msdrg-(?:v\d+-|core-)[\d\.]+\.jar",
            r"MCE-[\d\.]+-?[\d\.]+\.jar",
            r"mce-proto-[\d\.]+\.jar",
            r"Utility-[\d\.]+\.jar",
        ],
        "ioce": [r"ioce-standalone-[\d\.]+\.jar"],
        "hhag": ["HomeHealth.jar"],
        "cmg": ["CMG_550.jar", "irf-proto-1.2.0.jar", "gfc-base-factory-3.4.9.jar"],
        "pricers": [
            r"esrd-pricer-[\w\-\.]+(?:\.jar|\.zip)",
            r"fqhc-pricer-[\w\-\.]+(?:\.jar|\.zip)",
            r"hha-pricer-[\w\-\.]+(?:\.jar|\.zip)",
            r"hospice-pricer-[\w\-\.]+(?:\.jar|\.zip)",
            r"ipf-pricer-[\w\-\.]+(?:\.jar|\.zip)",
            r"ipps-pricer-[\w\-\.]+(?:\.jar|\.zip)",
            r"irf-pricer-[\w\-\.]+(?:\.jar|\.zip)",
            r"ltch-pricer-[\w\-\.]+(?:\.jar|\.zip)",
            r"opps-pricer-[\w\-\.]+(?:\.jar|\.zip)",
            r"snf-pricer-[\w\-\.]+(?:\.jar|\.zip)",
        ],
    }

    def __init__(
        self, jars_dir="jars", download_dir="downloads", log_level=logging.INFO
    ):
        """
        Initialize the CMS Downloader.

        Args:
            jars_dir (str): Directory to store JAR files
            download_dir (str): Temporary directory for downloads
            log_level (int): Logging level
        """
        self.jars_dir = jars_dir
        self.download_dir = download_dir
        self.pricers_dir = os.path.join(jars_dir, "pricers")

        # Setup logging
        self.logger = self._setup_logging(log_level)

    def _extract_msdrg_version_from_text(self, text, href):
        """
        Extract version number from MS-DRG text and URL for version comparison.

        Args:
            text (str): The text content from the <strong> element
            href (str): The download URL

        Returns:
            float: Version number for comparison (higher = newer)
        """
        try:
            # First try to extract version from the text (e.g., "Version 43")
            text_version_match = re.search(
                r"Version\s+(\d+(?:\.\d+)?)", text, re.IGNORECASE
            )
            if text_version_match:
                return float(text_version_match.group(1))

            # Try to extract from "V43" or "v43" pattern in text
            text_v_match = re.search(r"v(\d+(?:\.\d+)?)", text, re.IGNORECASE)
            if text_v_match:
                return float(text_v_match.group(1))

            # Fall back to URL-based extraction
            return self._extract_msdrg_version(href)

        except (ValueError, AttributeError):
            return 0.0

    def _extract_msdrg_version(self, href):
        """
        Extract version number from MS-DRG download URL for version comparison.

        Args:
            href (str): The download URL

        Returns:
            float: Version number for comparison (higher = newer)
        """
        try:
            # Pattern for v43 format: ms-drg-mce-v43-standalone-jars.zip
            v_match = re.search(r"v(\d+(?:\.\d+)?)", href, re.IGNORECASE)
            if v_match:
                return float(v_match.group(1))

            # Pattern for version in filename like v42.1
            version_match = re.search(r"(\d+\.\d+)", href)
            if version_match:
                return float(version_match.group(1))

            # Pattern for standalone version numbers
            standalone_match = re.search(r"(\d+)", href)
            if standalone_match:
                return float(standalone_match.group(1))

            # Default to 0 if no version found
            return 0.0

        except (ValueError, AttributeError):
            return 0.0

    def _setup_logging(self, log_level):
        """Setup logging configuration."""
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("cms_downloads.log"),
                logging.StreamHandler(),
            ],
        )
        return logging.getLogger("cms_downloader")

    def check_existing_jars(self):
        """
        Scan the jars directory and return sets of existing JAR files.

        Returns:
            dict: {'main': set(), 'pricers': set()} containing existing JAR filenames
        """
        existing = {"main": set(), "pricers": set()}

        # Check main jars directory
        if os.path.exists(self.jars_dir):
            for file in os.listdir(self.jars_dir):
                if file.endswith(".jar"):
                    existing["main"].add(file)

        # Check pricers subdirectory
        if os.path.exists(self.pricers_dir):
            for file in os.listdir(self.pricers_dir):
                if file.endswith(".jar"):
                    existing["pricers"].add(file)

        return existing

    def get_missing_jars_for_component(self, component, existing_jars=None):
        """
        Get missing JARs for a specific component.

        Args:
            component (str): Component name ('slf4j', 'gfc', 'grpc', etc.)
            existing_jars (dict): Optional pre-computed existing JARs

        Returns:
            list: Missing JAR filenames for the component
        """
        if existing_jars is None:
            existing_jars = self.check_existing_jars()

        if component not in self.REQUIRED_JARS:
            return []

        required = self.REQUIRED_JARS[component]

        if component == "pricers":
            existing = existing_jars["pricers"]
        else:
            existing = existing_jars["main"]

        if component in ["pricers", "ioce", "msdrg"]:
            missing = []
            for req_pattern in required:
                pattern = re.compile(req_pattern)
                if not any(pattern.match(jar) for jar in existing):
                    missing.append(req_pattern)
            return missing
        else:
            missing = set(required) - set(existing)
            return list(missing)

    def is_component_complete(self, component, existing_jars=None):
        """
        Check if all JARs for a component are present.

        Args:
            component (str): Component name
            existing_jars (dict): Optional pre-computed existing JARs

        Returns:
            bool: True if component is complete
        """
        missing = self.get_missing_jars_for_component(component, existing_jars)
        return len(missing) == 0

    def get_all_missing_jars(self):
        """
        Get all missing JARs across all components.

        Returns:
            dict: {component: [missing_jars]} for components with missing JARs
        """
        existing_jars = self.check_existing_jars()
        missing_by_component = {}

        for component in self.REQUIRED_JARS.keys():
            missing = self.get_missing_jars_for_component(component, existing_jars)
            if missing:
                missing_by_component[component] = missing

        return missing_by_component

    def create_directory(self, directory):
        """Create a directory if it doesn't exist."""
        try:
            os.makedirs(directory, exist_ok=True)
            self.logger.info(f"Created directory: {directory}")
        except Exception as e:
            self.logger.error(f"Failed to create directory {directory}: {str(e)}")
            raise

    def download_file(self, url, filename, directory=None):
        """Download a file with progress bar."""
        if directory is None:
            directory = self.download_dir

        try:
            headers = {"User-Agent": self.USER_AGENT}
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            file_path = os.path.join(directory, filename)

            with (
                open(file_path, "wb") as f,
                tqdm(
                    desc=filename,
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                ) as bar,
            ):
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        size = f.write(chunk)
                        bar.update(size)

            self.logger.info(f"Successfully downloaded: {filename}")
            return file_path
        except Exception as e:
            self.logger.error(f"Error downloading {url}: {str(e)}")
            return None

    def get_filename_from_url(self, url):
        """Extract filename from URL."""
        return url.split("/")[-1]

    def download_slf4j_jar(self):
        """Download SLF4J JAR files."""
        try:
            self.logger.info(
                f"Downloading SLF4J JAR file from: {self.SLF4J_JAR} and {self.SLF4J_JAR2}"
            )
            path_1 = self.download_file(self.SLF4J_JAR, "slf4j-simple-2.0.9.jar")
            path_2 = self.download_file(self.SLF4J_JAR2, "slf4j-api-2.0.9.jar")
            return [path_1, path_2]
        except Exception as e:
            self.logger.error(f"Error downloading SLF4J JAR file: {str(e)}")
            return None

    def process_slf4j_jar(self, force_download=False):
        """Process the SLF4J JAR file."""
        try:
            # Check if SLF4J JARs already exist
            if not force_download and self.is_component_complete("slf4j"):
                self.logger.info("SLF4J JARs already exist, skipping download")
                return

            slf4j_jar_paths = self.download_slf4j_jar()
            if not slf4j_jar_paths:
                self.logger.error("SLF4J JAR file not found")
                return

            # Move the JAR file to the jars directory
            for path in slf4j_jar_paths:
                if path:
                    dest_path = os.path.join(self.jars_dir, os.path.basename(path))
                    shutil.move(path, dest_path)
                    self.logger.info(
                        f"Moved SLF4J JAR file to jars directory: {os.path.basename(path)}"
                    )
        except Exception as e:
            self.logger.error(f"Error processing SLF4J JAR file: {str(e)}")

    def download_gfc_jar(self):
        """Download the GFC Base API JAR file."""
        try:
            self.logger.info(f"Downloading GFC Base API JAR file from: {self.GFC_JAR}")
            return self.download_file(self.GFC_JAR, "gfc-base-api-3.4.9.jar")
        except Exception as e:
            self.logger.error(f"Error downloading GFC Base API JAR file: {str(e)}")
            return None

    def download_grpc_jar(self):
        """Download GRPC JAR files."""
        try:
            self.logger.info(
                f"Downloading GRPC JAR file from: {self.GRPC_JAR1} and {self.GRPC_JAR2}"
            )
            path_1 = self.download_file(self.GRPC_JAR1, "protobuf-java-3.22.2.jar")
            path_2 = self.download_file(self.GRPC_JAR2, "protobuf-java-3.21.7.jar")
            return [path_1, path_2]
        except Exception as e:
            self.logger.error(f"Error downloading GRPC JAR file: {str(e)}")
            return None

    def process_gfc_jar(self, force_download=False):
        """Process the GFC Base API JAR file."""
        try:
            # Check if GFC JAR already exists
            if not force_download and self.is_component_complete("gfc"):
                self.logger.info("GFC JAR already exists, skipping download")
                return

            gfc_jar_path = self.download_gfc_jar()
            if not gfc_jar_path:
                self.logger.error("GFC JAR file not found")
                return

            # Move the JAR file to the jars directory
            dest_path = os.path.join(self.jars_dir, "gfc-base-api-3.4.9.jar")
            shutil.move(gfc_jar_path, dest_path)
            self.logger.info("Moved GFC JAR file to jars directory")
        except Exception as e:
            self.logger.error(f"Error processing GFC JAR file: {str(e)}")

    def process_grpc_jar(self, force_download=False):
        """Process the GRPC JAR file."""
        try:
            # Check if GRPC JARs already exist
            if not force_download and self.is_component_complete("grpc"):
                self.logger.info("GRPC JARs already exist, skipping download")
                return

            grpc_jar_paths = self.download_grpc_jar()
            if not grpc_jar_paths:
                self.logger.error("GRPC JAR file not found")
                return

            # Move the JAR file to the jars directory
            for path in grpc_jar_paths:
                if path:
                    dest_path = os.path.join(self.jars_dir, os.path.basename(path))
                    shutil.move(path, dest_path)
                    self.logger.info(
                        f"Moved GRPC JAR file to jars directory: {os.path.basename(path)}"
                    )
        except Exception as e:
            self.logger.error(f"Error processing GRPC JAR file: {str(e)}")

    def map_url_to_jar_filename(self, url):
        """
        Map a download URL to the expected JAR filename.

        Args:
            url (str): The download URL

        Returns:
            str: The expected JAR filename, or None if not mappable
        """
        try:
            filename = self.get_filename_from_url(url)

            # Updated pattern matching for pricer URLs
            # Example: ipps-pricer-2026-0-v2-11-0-executable-jar.zip
            pricer_pattern = (
                r"(\w+)-pricer-(\d+(?:-\d+)*)-v(\d+(?:-\d+)*)-executable(?:-jar)?\.zip"
            )
            match = re.match(pricer_pattern, filename)

            if match:
                pricer_type = match.group(1)
                _main_version = match.group(2)  # e.g., "2026-0" currently unused
                sub_version = match.group(3)  # e.g., "2-11-0"

                # Convert sub_version to dotted format
                version = sub_version.replace("-", ".")

                jar_filename = f"{pricer_type}-pricer-application-{version}.jar"
                return jar_filename

            return None

        except Exception as e:
            self.logger.error(f"Error mapping URL to JAR filename: {str(e)}")
            return None

    def process_zip_for_jars(
        self, zip_path, prefix="", dest_dir=None, missing_jars=None
    ):
        """
        Process a ZIP file to extract JAR files with an optional prefix.

        Args:
            zip_path (str): Path to the ZIP file to process
            prefix (str): Optional prefix for the component (e.g., "msdrg", "ioce", "pricer")
            dest_dir (str): Destination directory for JAR files
            missing_jars (list): Optional list of missing JAR filenames. If provided,
                               only these JARs will be moved from the ZIP.
        """
        if dest_dir is None:
            dest_dir = self.jars_dir

        if not zip_path or not os.path.exists(zip_path):
            self.logger.error(f"ZIP file not found: {zip_path}")
            return
        self.create_directory(dest_dir)

        zip_filename = os.path.basename(zip_path)
        self.logger.info(f"Processing ZIP file: {zip_filename}")

        if missing_jars:
            self.logger.info(f"Looking for specific missing JARs: {missing_jars}")
        else:
            self.logger.info("Processing all JAR files from ZIP")

        # Create a unique temporary directory for extraction
        temp_extract_dir = tempfile.mkdtemp(
            prefix="temp_extract_", dir=self.download_dir
        )

        try:
            # Extract the ZIP file
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_extract_dir)

            # Find any nested ZIP files
            nested_zips = glob.glob(
                os.path.join(temp_extract_dir, "**", "*.zip"), recursive=True
            )
            self.logger.info(f"Found {len(nested_zips)} nested ZIP files in package")

            # Process each nested ZIP
            for nested_zip in nested_zips:
                nested_zip_name = os.path.basename(nested_zip)
                self.logger.info(f"Extracting nested ZIP: {nested_zip_name}")

                # Create a subdirectory for this nested ZIP
                nested_extract_dir = os.path.join(
                    temp_extract_dir, f"nested_{nested_zip_name.split('.')[0]}"
                )
                self.create_directory(nested_extract_dir)

                # Extract the nested ZIP
                with zipfile.ZipFile(nested_zip, "r") as zip_ref:
                    zip_ref.extractall(nested_extract_dir)

            # Find all JAR files from both the main extraction and nested extractions
            all_jar_files = glob.glob(
                os.path.join(temp_extract_dir, "**", "*.jar"), recursive=True
            )
            self.logger.info(
                f"Found {len(all_jar_files)} JAR files in {prefix} package"
            )

            # Move JAR files to jars directory
            jar_count = 0
            skipped_count = 0

            for jar_file in all_jar_files:
                jar_filename = os.path.basename(jar_file)
                dest_path = os.path.join(dest_dir, jar_filename)

                # If we have a specific list of missing JARs, only move those
                if missing_jars is not None:
                    use_regex = prefix in ["ioce", "msdrg"]
                    is_in_missing_list = False
                    if use_regex:
                        if any(
                            re.match(pattern, jar_filename) for pattern in missing_jars
                        ):
                            is_in_missing_list = True
                    elif jar_filename in missing_jars:
                        is_in_missing_list = True

                    if not is_in_missing_list:
                        self.logger.info(
                            f"Skipping {jar_filename} - not in missing JARs list"
                        )
                        skipped_count += 1
                        continue

                # Check if the file already exists
                if os.path.exists(dest_path):
                    if missing_jars is not None:
                        # This shouldn't happen if our missing_jars logic is correct, but handle it gracefully
                        self.logger.warning(
                            f"JAR {jar_filename} was listed as missing but already exists at destination"
                        )
                        skipped_count += 1
                        continue
                    else:
                        # Legacy behavior: add prefix and timestamp for backward compatibility
                        base, ext = os.path.splitext(jar_filename)
                        jar_filename = f"{base}_{prefix}_{int(time.time())}{ext}"
                        dest_path = os.path.join(dest_dir, jar_filename)

                # Move the JAR file
                shutil.move(jar_file, dest_path)
                self.logger.info(f"Moved {prefix} JAR file: {jar_filename}")
                jar_count += 1

            if missing_jars is not None:
                self.logger.info(
                    f"{prefix} JAR extraction complete. Moved {jar_count} missing JAR files, skipped {skipped_count} existing ones."
                )
            else:
                self.logger.info(
                    f"{prefix} JAR extraction complete. Moved {jar_count} JAR files to {dest_dir} directory."
                )

        except Exception as e:
            self.logger.error(f"Error processing ZIP file {zip_filename}: {str(e)}")
        finally:
            # Clean up temporary directory
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir, ignore_errors=True)

    def download_msdrg_files(self):
        """Download MS-DRG Java source files from the MS-DRG website."""
        try:
            self.logger.info(f"Fetching MS-DRG files from: {self.MSDRG_URL}")
            response = requests.get(
                self.MSDRG_URL, headers={"User-Agent": self.USER_AGENT}
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Look for links that contain <strong> elements with "Java Source Code" text
            java_source_links = []

            for link in soup.find_all("a", href=True):
                # Check if the link contains a <strong> element with "Java Source Code"
                strong_elements = link.find_all("strong")
                for strong in strong_elements:
                    if strong.get_text() and "Java Source Code" in strong.get_text():
                        href = link.get("href", "")
                        if href and (".zip" in href.lower()):
                            # Extract version number from the strong text or href
                            version = self._extract_msdrg_version_from_text(
                                strong.get_text(), href
                            )
                            java_source_links.append(
                                {
                                    "href": href,
                                    "version": version,
                                    "text": strong.get_text().strip(),
                                }
                            )
                            self.logger.info(
                                f"Found MS-DRG Java Source: {href} (version {version}) - {strong.get_text()[:100]}..."
                            )
                            break

            if not java_source_links:
                self.logger.error("No MS-DRG Java Source Code links found")
                return False

            # Sort by version (highest first) and take the newest
            java_source_links.sort(key=lambda x: x["version"], reverse=True)
            selected = java_source_links[0]

            self.logger.info(
                f"Selected MS-DRG file: {selected['href']} (version {selected['version']})"
            )

            # Download the selected file
            if selected["href"].startswith("/"):
                download_url = urljoin("https://www.cms.gov", selected["href"])
            else:
                download_url = selected["href"]

            filename = os.path.basename(selected["href"])
            # Handle various zip filename suffixes that CMS uses
            if filename.endswith((".zip-11", ".zip-1", ".zip-2")):
                # Remove numeric suffixes for local storage
                filename = re.sub(r"\.zip-\d+$", ".zip", filename)

            success = self.download_file(download_url, filename, self.download_dir)
            if success:
                zip_path = os.path.join(self.download_dir, filename)
                missing_jars = self.get_missing_jars_for_component("msdrg")
                self.process_zip_for_jars(zip_path, "msdrg", missing_jars=missing_jars)
                return zip_path
            else:
                self.logger.error("Failed to download MS-DRG Java Source file")
                return False

        except Exception as e:
            self.logger.error(f"Error downloading MS-DRG files: {e}")
            return False

    def download_ioce_files(self):
        """Download IOCE Editor Java files."""
        try:
            self.logger.info(f"Connecting to IOCE website: {self.IOCE_URL}")
            session = requests.Session()
            headers = {"User-Agent": self.USER_AGENT}

            # First request to find the java-standalone link
            response = session.get(self.IOCE_URL, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Find the link with "java-standalone" text
            java_standalone_link = None
            for link in soup.find_all("a"):
                href = link.get("href", "")
                inner_text = link.get_text()
                if (
                    self.JAVA_STANDALONE_PATTERN in href.lower()
                    or "Java Standalone" in inner_text
                ):
                    java_standalone_link = href
                    self.logger.info(
                        f"Found IOCE standalone Java link: {java_standalone_link}"
                    )
                    break

            if not java_standalone_link:
                self.logger.error(
                    f"Could not find '{self.JAVA_STANDALONE_PATTERN}' link on the IOCE page"
                )
                return None

            # Follow the link to the license agreement page
            license_url = urljoin(self.IOCE_URL, java_standalone_link)
            license_response = session.get(license_url, headers=headers)
            license_response.raise_for_status()

            license_soup = BeautifulSoup(license_response.content, "html.parser")

            # Find the form with the "agree" button
            form = None
            for form_tag in license_soup.find_all("form"):
                if form_tag.find("input", attrs={"name": "agree"}):
                    form = form_tag
                    break

            if not form:
                self.logger.error("Could not find license agreement form")
                return None

            # Get the form action URL
            form_action = form.get("action", "")
            if not form_action:
                self.logger.error("Could not find form action URL")
                return None

            form_url = urljoin(license_url, form_action)

            # Extract all form data - includes hidden fields
            form_data = {}
            for input_tag in form.find_all("input"):
                name = input_tag.get("name")
                value = input_tag.get("value", "")
                if name:
                    form_data[name] = value

            # Make sure we have the 'agree' value
            form_data["agree"] = "Yes"

            # Submit the form to download the file
            self.logger.info("Submitting license agreement form")
            download_response = session.post(
                form_url, data=form_data, headers=headers, stream=True
            )
            download_response.raise_for_status()

            # Get the filename from Content-Disposition header if available
            content_disposition = download_response.headers.get(
                "Content-Disposition", ""
            )
            filename = ""
            if "filename=" in content_disposition:
                filename = re.findall("filename=(.+)", content_disposition)[0].strip(
                    "\"'"
                )

            # If no filename in header, use a default
            if not filename:
                filename = f"ioce_java_standalone_{int(time.time())}.zip"

            # Save the file
            file_path = os.path.join(self.download_dir, filename)
            with (
                open(file_path, "wb") as f,
                tqdm(
                    desc=filename,
                    total=int(download_response.headers.get("content-length", 0)),
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                ) as bar,
            ):
                for chunk in download_response.iter_content(chunk_size=1024):
                    if chunk:
                        size = f.write(chunk)
                        bar.update(size)

            self.logger.info(f"Successfully downloaded IOCE file: {filename}")
            return file_path

        except Exception as e:
            self.logger.error(f"Error downloading IOCE files: {str(e)}")
            return None

    def download_hhagrouper_files(self):
        # find the first href that contains hh-pps-grouper-software and ends with .zip
        try:
            self.logger.info(f"Connecting to HHAGrouper website: {self.HHAG_URL}")
            headers = {"User-Agent": self.USER_AGENT}
            response = requests.get(self.HHAG_URL, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Find the link to hh-pps-grouper-software.zip
            hh_link = None
            for link in soup.find_all(
                "a", href=re.compile(r"hh-pps-grouper-software.*\.zip")
            ):
                # if the link contains -gui go to the next
                if "-gui" in link["href"]:
                    continue
                hh_link = link["href"]
                break

            if not hh_link:
                self.logger.error(
                    "Could not find 'hh-pps-grouper-software' link on the HHAGrouper page"
                )
                return None

            # Download the hh-pps-grouper-software zip file
            full_url = urljoin(self.HHAG_URL, hh_link)
            filename = self.get_filename_from_url(
                full_url
            )  # <-- CMS names the zip files generically like "2025.zip", so we'll add to the filename
            filename = f"hhgs-{filename}"

            self.logger.info(f"Found HHAGrouper zip: {filename} with link: {full_url}")
            return self.download_file(full_url, filename)
        except Exception as e:
            self.logger.error(f"Error downloading HHAGrouper files: {str(e)}")
            return None

    def process_hhagrouper_zip(self, zip_path):
        # find the HomeHealth.jar file and move it to the jars directory
        if not zip_path or not os.path.exists(zip_path):
            self.logger.error(f"ZIP file not found: {zip_path}")
            return
        zip_filename = os.path.basename(zip_path)
        self.logger.info(f"Processing HHAGrouper ZIP file: {zip_filename}")
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Extract all files to a temporary directory
                temp_extract_dir = os.path.join(
                    self.download_dir, f"temp_extract_{int(time.time())}"
                )
                self.create_directory(temp_extract_dir)
                zip_ref.extractall(temp_extract_dir)

                # Find the HomeHealth.jar file
                jar_files = glob.glob(
                    os.path.join(temp_extract_dir, "**", "HomeHealth.jar"),
                    recursive=True,
                )
                if not jar_files:
                    self.logger.error(
                        "Could not find HomeHealth.jar in the HHAGrouper ZIP"
                    )
                    return

                # Move the HomeHealth.jar file to the jars directory
                for jar_file in jar_files:
                    dest_path = os.path.join(self.jars_dir, "HomeHealth.jar")
                    shutil.move(jar_file, dest_path)
                    self.logger.info(f"Moved HomeHealth.jar to {dest_path}")
            self.logger.info("HHAGrouper JAR extraction complete")
        except Exception as e:
            self.logger.error(
                f"Error processing HHAGrouper ZIP file {zip_filename}: {str(e)}"
            )

    def download_cmg_grouper(self):
        """Download the CMG Grouper ZIP file."""
        try:
            headers = {"User-Agent": self.USER_AGENT}
            response = requests.get(self.CMG_URL, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Find the link to the CMG Grouper ZIP file
            cmg_link = None
            # example /files/zip/cmg-version-530-final.zip
            for link in soup.find_all(
                "a", href=re.compile(r"/files/zip/cmg-version-\d+-final\.zip")
            ):
                cmg_link = link["href"]
                break

            if not cmg_link:
                self.logger.error("Could not find 'cmg-grouper' link on the CMS page")
                return None

            # Download the CMG Grouper ZIP file
            full_url = urljoin(self.CMG_URL, cmg_link)
            filename = self.get_filename_from_url(full_url)
            self.logger.info(f"Found CMG Grouper zip: {filename} with link: {full_url}")
            return self.download_file(full_url, filename)
        except Exception as e:
            self.logger.error(f"Error downloading CMG Grouper files: {str(e)}")
            return None

    def process_cmggrouper_zip(self, zip_path):
        """
        CMG Zip file contains 2 sub .zip files
         1.) CMG JAR.zip
         2.) CMG_v{version}_LIB.zip

         from CMG JAR.zip we'll extract the CMG_<version>.jar
         from CMG_v{version}_LIB.zip we'll extract all jars, compare them
         to what's already in the jars directory, if a jar does not exist we'll
         place that into the jars directory, otherwise we'll skip it.
        """

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(self.download_dir)

        # Process the extracted ZIP files
        zip_files = glob.glob(os.path.join(self.download_dir, "*.zip"))
        for zip_file in zip_files:
            self.process_zip_for_jars(
                zip_file, "cmg", self.jars_dir, self.REQUIRED_JARS["cmg"]
            )

    def extract_jar_files(self, dest_dir=None):
        """Extract JAR files from downloaded ZIP files and move them to jars directory."""
        if dest_dir is None:
            dest_dir = self.jars_dir

        try:
            # Create jars directory
            self.create_directory(dest_dir)

            # Get list of all ZIP files in the download directory
            zip_files = glob.glob(os.path.join(self.download_dir, "*.zip"))
            if "pricers" in dest_dir:
                # restrict zip files to those containing "pricer" in the name
                zip_files = [
                    zf for zf in zip_files if "pricer" in os.path.basename(zf).lower()
                ]
            self.logger.info(f"Found {len(zip_files)} ZIP files to process")

            for zip_file in zip_files:
                # Skip the MSDRG, HHA Grouper and IOCE files as they are processed separately
                zip_filename = os.path.basename(zip_file)
                if (
                    self.JAVA_SOURCE_PATTERN in zip_filename
                    or self.JAVA_STANDALONE_PATTERN in zip_filename
                    or "hhgs" in zip_filename.lower()
                ):
                    continue

                self.process_zip_for_jars(zip_file, "pricer", dest_dir)

            self.logger.info("JAR extraction from pricer ZIPs complete")
        except Exception as e:
            self.logger.error(f"An error occurred during JAR extraction: {str(e)}")

    def download_web_pricers(self, download_dir=None, force_all_downloads=False):
        """
        Main function to scrape the CMS website and download files.

        Args:
            download_dir (str): Directory to download files to
            force_all_downloads (bool): If True, download all files regardless of existing JARs.
                                      If False, only download files for missing JARs.
        """
        if download_dir is None:
            download_dir = self.download_dir

        try:
            headers = {"User-Agent": self.USER_AGENT}
            response = requests.get(self.CMS_URL, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Find the target header
            target_section = None
            for h2 in soup.find_all("h2"):
                if self.TARGET_HEADER in h2.text:
                    target_section = h2
                    break

            if not target_section:
                self.logger.error(
                    f"Could not find section with header: {self.TARGET_HEADER}"
                )
                return

            # Look at content following the header until we hit another h2 or reach the end
            download_links = []
            current = target_section.next_sibling

            while current and (not current.name or current.name != "h2"):
                if current.name == "a" and self.ZIP_PATH_PATTERN in current.get(
                    "href", ""
                ):
                    download_links.append(current["href"])
                elif hasattr(current, "find_all"):
                    for link in current.find_all(
                        "a", href=re.compile(self.ZIP_PATH_PATTERN)
                    ):
                        download_links.append(link["href"])
                current = current.next_sibling

            if not download_links:
                self.logger.warning("No download links found matching the criteria")
                return

            self.logger.info(f"Found {len(download_links)} potential files to download")

            # Create pricers subdirectory as requested by user
            pricers_dir = os.path.join(self.jars_dir, "pricers")
            self.create_directory(pricers_dir)

            # If not forcing all downloads, filter links based on missing JARs
            if not force_all_downloads:
                missing_jars = self.get_missing_jars_for_component("pricers")
                if not missing_jars:
                    self.logger.info(
                        "All pricer JARs are already present. Use force_all_downloads=True to redownload."
                    )
                    return

                self.logger.info(f"Missing JAR files: {missing_jars}")

                # Filter download links to only include those for missing JARs
                filtered_links = []
                for link in download_links:
                    full_url = urljoin(self.CMS_URL, link)
                    expected_jar = self.map_url_to_jar_filename(full_url)

                    if expected_jar and any(
                        re.match(pattern, expected_jar) for pattern in missing_jars
                    ):
                        filtered_links.append(link)
                        self.logger.info(
                            f"Will download {self.get_filename_from_url(full_url)} for missing JAR: {expected_jar}"
                        )
                    elif expected_jar:
                        self.logger.info(
                            f"Skipping {self.get_filename_from_url(full_url)} as a matching JAR already exists"
                        )
                    else:
                        self.logger.warning(
                            f"Could not map URL {full_url} to expected JAR filename"
                        )

                download_links = filtered_links

                if not download_links:
                    self.logger.info(
                        "No downloads needed - all required JARs are present"
                    )
                    return

            self.logger.info(f"Will download {len(download_links)} files")

            # Download each file
            success_count = 0
            for link in download_links:
                full_url = urljoin(self.CMS_URL, link)
                filename = self.get_filename_from_url(full_url)

                self.logger.info(f"Downloading: {filename} from {full_url}")
                if self.download_file(full_url, filename):
                    success_count += 1
                    # Add a small delay between downloads to be nice to the server
                    time.sleep(1)

            self.logger.info(
                f"Download complete. Successfully downloaded {success_count} of {len(download_links)} files."
            )
            self.extract_jar_files(dest_dir=pricers_dir)

        except Exception as e:
            self.logger.error(f"An error occurred: {str(e)}")

    def list_jar_inventory(self):
        """
        Report current JAR status by component.

        Returns:
            dict: Detailed inventory of JAR status by component
        """
        existing_jars = self.check_existing_jars()
        inventory = {
            "summary": {
                "main_jars_count": len(existing_jars["main"]),
                "pricer_jars_count": len(existing_jars["pricers"]),
                "components_complete": 0,
                "components_missing": 0,
            },
            "components": {},
            "existing_jars": existing_jars,
        }

        for component in self.REQUIRED_JARS.keys():
            is_complete = self.is_component_complete(component, existing_jars)
            missing = self.get_missing_jars_for_component(component, existing_jars)

            inventory["components"][component] = {
                "complete": is_complete,
                "missing_jars": missing,
                "jar_count": len(self.REQUIRED_JARS[component])
                if component in ["slf4j", "gfc", "grpc"]
                else "variable",
            }

            if is_complete:
                inventory["summary"]["components_complete"] += 1
            else:
                inventory["summary"]["components_missing"] += 1

        return inventory

    def validate_jar_environment(self):
        """
        Comprehensive check if JAR environment is complete.

        Returns:
            dict: Validation results with status and details
        """
        missing_components = self.get_all_missing_jars()
        is_valid = len(missing_components) == 0

        validation_result = {
            "is_valid": is_valid,
            "missing_components": missing_components,
            "total_components": len(self.REQUIRED_JARS),
            "complete_components": len(self.REQUIRED_JARS) - len(missing_components),
            "status_message": "Environment is complete"
            if is_valid
            else f"Missing {len(missing_components)} components",
        }

        return validation_result

    def print_jar_inventory(self):
        """Print a formatted report of the JAR inventory."""
        inventory = self.list_jar_inventory()

        print("\n=== JAR Environment Inventory ===")
        print(f"Main directory JARs: {inventory['summary']['main_jars_count']}")
        print(f"Pricer directory JARs: {inventory['summary']['pricer_jars_count']}")
        print(f"Complete components: {inventory['summary']['components_complete']}")
        print(f"Missing components: {inventory['summary']['components_missing']}")

        print("\n=== Component Status ===")
        for component, status in inventory["components"].items():
            status_icon = "✓" if status["complete"] else "✗"
            print(
                f"{status_icon} {component.upper()}: {'Complete' if status['complete'] else 'Missing'}"
            )
            if not status["complete"] and status["missing_jars"]:
                for jar in status["missing_jars"]:
                    print(f"    - Missing: {jar}")

        if inventory["existing_jars"]["main"]:
            print(
                f"\n=== Main JAR Files ({len(inventory['existing_jars']['main'])}) ==="
            )
            for jar in sorted(inventory["existing_jars"]["main"]):
                print(f"  - {jar}")

        if inventory["existing_jars"]["pricers"]:
            print(
                f"\n=== Pricer JAR Files ({len(inventory['existing_jars']['pricers'])}) ==="
            )
            for jar in sorted(inventory["existing_jars"]["pricers"]):
                print(f"  - {jar}")

    def build_jar_environment(self, clean_existing=True, force_download=False):
        """Main method to build the complete JAR environment needed for processing."""
        try:
            # If clean_existing=True, delete everything and start fresh
            if clean_existing:
                if os.path.exists(self.jars_dir):
                    shutil.rmtree(self.jars_dir)
                os.makedirs(self.jars_dir, exist_ok=True)
                force_all_downloads = True  # Force all downloads when cleaning
            else:
                self.create_directory(self.jars_dir)
                force_all_downloads = force_download

            self.logger.info("Starting CMS Software download process")

            # Log current environment status
            if not clean_existing:
                missing_jars = self.get_all_missing_jars()
                if not missing_jars:
                    self.logger.info("All JAR components are already present")
                else:
                    self.logger.info(f"Missing components: {list(missing_jars.keys())}")

            # Create directories
            self.create_directory(self.download_dir)
            self.create_directory(self.jars_dir)

            # Download and process MSDRG files
            if force_all_downloads or not self.is_component_complete("msdrg"):
                self.logger.info("Starting MSDRG file download process")
                msdrg_zip_path = self.download_msdrg_files()
                if msdrg_zip_path:
                    self.logger.info("Processing MSDRG ZIP file")
                    if force_all_downloads:
                        # Process all JARs from the ZIP
                        self.process_zip_for_jars(msdrg_zip_path, "msdrg")
                    else:
                        # Only process missing JARs
                        missing_msdrg_jars = self.get_missing_jars_for_component(
                            "msdrg"
                        )
                        self.process_zip_for_jars(
                            msdrg_zip_path, "msdrg", missing_jars=missing_msdrg_jars
                        )
            else:
                self.logger.info("MSDRG components already exist, skipping download")

            # Download and process IOCE files
            if force_all_downloads or not self.is_component_complete("ioce"):
                self.logger.info("Starting IOCE file download process")
                ioce_zip_path = self.download_ioce_files()
                if ioce_zip_path:
                    self.logger.info("Processing IOCE ZIP file")
                    if force_all_downloads:
                        # Process all JARs from the ZIP
                        self.process_zip_for_jars(ioce_zip_path, "ioce")
                    else:
                        # Only process missing JARs
                        missing_ioce_jars = self.get_missing_jars_for_component("ioce")
                        self.process_zip_for_jars(
                            ioce_zip_path, "ioce", missing_jars=missing_ioce_jars
                        )
            else:
                self.logger.info("IOCE components already exist, skipping download")

            # Download and process the HHAG files
            if force_all_downloads or not self.is_component_complete("hhag"):
                self.logger.info("Starting HHAGrouper file download process")
                hhag_zip_path = self.download_hhagrouper_files()
                if hhag_zip_path:
                    self.logger.info("Processing HHAGrouper ZIP file")
                    if force_all_downloads:
                        # Process all JARs from the ZIP
                        self.process_zip_for_jars(hhag_zip_path, "HomeHealth")
                    else:
                        # Only process missing JARs
                        missing_hhag_jars = self.get_missing_jars_for_component("hhag")
                        self.process_zip_for_jars(
                            hhag_zip_path, "HomeHealth", missing_jars=missing_hhag_jars
                        )
            else:
                self.logger.info(
                    "HHAGrouper components already exist, skipping download"
                )

            # Process individual JAR components
            self.process_gfc_jar(force_download=force_all_downloads)
            self.process_grpc_jar(force_download=force_all_downloads)
            self.process_slf4j_jar(force_download=force_all_downloads)

            # Download and process the CMG Grouper files
            if force_all_downloads or not self.is_component_complete("cmg"):
                self.logger.info("Starting CMGrouper file download process")
                cmg_zip_path = self.download_cmg_grouper()
                if cmg_zip_path:
                    self.logger.info("Processing CMGrouper ZIP file")
                    if force_all_downloads:
                        # Process all JARs from the ZIP
                        self.process_cmggrouper_zip(cmg_zip_path)
                    else:
                        # Only process missing JARs
                        missing_cmg_jars = self.get_missing_jars_for_component("cmg")
                        self.process_zip_for_jars(
                            cmg_zip_path, "CMGrouper", missing_jars=missing_cmg_jars
                        )
            else:
                self.logger.info(
                    "CMGrouper components already exist, skipping download"
                )

            # Get CMS Web Pricers - these go in their own subdirectory
            if force_all_downloads:
                self.logger.info("Starting CMS Web Pricers download process")
                self.logger.info("Force all downloads is True")
                self.download_web_pricers(force_all_downloads=force_all_downloads)

            if not self.is_component_complete("pricers"):
                self.logger.info("Starting CMS Web Pricers download process")
                self.logger.info(
                    "Skipping download of CMS Web Pricers as they are already present"
                )
                self.download_web_pricers()
            else:
                self.logger.info("Pricer components already exist, skipping download")

            # Clean up download directory
            if os.path.exists(self.download_dir):
                shutil.rmtree(self.download_dir)

            # Remove sources jar files
            sources_jar_files = glob.glob(os.path.join(self.jars_dir, "*source*.jar"))
            gui_jar_files = glob.glob(os.path.join(self.jars_dir, "*GUI*.jar"))
            sources_jar_files.extend(gui_jar_files)
            for jar_file in sources_jar_files:
                os.remove(jar_file)
                self.logger.info(f"Removed sources JAR file: {jar_file}")

            self.logger.info("JAR environment build complete!")
            return True

        except Exception as e:
            self.logger.error(f"An unhandled error occurred: {str(e)}")
            if os.path.exists(self.download_dir):
                shutil.rmtree(self.download_dir)
            return False


if __name__ == "__main__":
    # Create downloader instance and build the JAR environment
    downloader = CMSDownloader()

    # Show current inventory before building
    print("Checking current JAR environment...")
    downloader.print_jar_inventory()

    # Build with selective downloading (default behavior)
    success = downloader.build_jar_environment(clean_existing=False)

    if success:
        print("\nJAR environment build completed successfully!")
        # Show final inventory
        downloader.print_jar_inventory()

        # Validate the environment
        validation = downloader.validate_jar_environment()
        print(f"\nEnvironment Validation: {validation['status_message']}")
    else:
        print("JAR environment build failed. Check logs for details.")

    # Uncomment to force clean rebuild:
    # success = downloader.build_jar_environment(clean_existing=True)
