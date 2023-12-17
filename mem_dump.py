# CD/DVD/BD Drive Memory Dumper
# Version: 2023-12-17
# Author: ehw
# Hidden-Palace.org R&D
# Description: Description: Attempts to create a memory dump using the user specified 3 byte SCSI opcode consisting of 16MB
# Notes: Script has been written for use with Windows 10 x64 and Python 3.11.4.

import subprocess
import win32api
import win32com.client
import sys
import os
import shutil
from datetime import datetime
import time
import glob
from tqdm import tqdm
import signal
from itertools import accumulate
import py7zr
import hashlib
from collections import defaultdict
import re

drive_letter = ""
opcode = ""

class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        self.log = open("memdump_logfile.log", "a")
   
    def write(self, message):
        self.terminal.write(message)
        if not self.log.closed:
          self.log.write(message)  

    def flush(self):
        pass    

class SkipException(Exception):
    pass

def keyboard_interrupt_handler(signal, frame):
    raise SkipException("User interrupted the process. Skipping...")

# Set up the interrupt handler
signal.signal(signal.SIGINT, keyboard_interrupt_handler)

sys.stdout = Logger()

def zip_files():
    zip_filename = "upload_me.7z"
    files_to_zip = glob.glob("*.bin") + ["memdump_logfile.log"]

    with py7zr.SevenZipFile(zip_filename, 'w') as zip_file:
        for file in files_to_zip:
            zip_file.write(file)
    
    print(f"Files zipped successfully into '{zip_filename}'. Please send this 7z file for analysis.")

def execute_command(command):
    with open('sg_raw_temp.txt', 'w') as output_file:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=output_file)
        _, stderr = process.communicate()

    stderr_str = stderr.decode('utf-8') if stderr is not None else ""

    with open('sg_raw_temp.txt', 'r') as temp_file:
        output = temp_file.read()
    
    if "Unaligned write command" in output:
        print("\nTimeout occurred...rereading LBA 0 to store it onto the cache again...")
        read_lba_0(drive_letter)

    
    return process.returncode, output.strip(), stderr_str.strip()

def dvd_drive_exists(drive_letter):
    drive_path = drive_letter + ':\\'
    return os.path.isdir(drive_path)

def read_lba_0(drive_letter):
    return
    print("Reading LBA 0 to store on the cache")
    command = f"sg_raw.exe -o lba_0_2048.bin -r 2048 {drive_letter}: a8 00 00 00 00 00 00 00 00 01 00 00"
    execute_command(command)

def mem_dump(opcode, drive_letter):
    read_lba_0(drive_letter) #might make this optional
    try:
        # Generate an array with sums of 16128 starting from 0 and ending with 16773120
        # This is technically the maximum amount that can be returned since the offset part of the CDB is only 3 bytes long
        # but no drive should have more than 16mb of RAM.
        start = 0
        end = 16773120
        step = 16128
        array_size = (end // step) + 1

        result_array = []

        for i in range(array_size):
            current_sum = start + (i * step)

            # Format the sum as a fixed 3-byte hexadecimal number
            hex_string = "{:06X}".format(current_sum)

            # Split the hex string into 2-byte chunks
            hex_chunks = [hex_string[j:j+2] for j in range(0, len(hex_string), 2)]

            # Join the chunks with spaces and append to the result array
            result_array.append(" ".join(hex_chunks))
        

        print(f"Attempting to dump the entirety of this drive's RAM by using {opcode}...")

        # Loop 1040 times
        total_iterations = 1040
        progress_bar = tqdm(total=total_iterations, desc="Memory Dump Progress", position=0)

        # Create a directory for temporary files
        temp_directory = "memdump_temp"
        os.makedirs(temp_directory, exist_ok=True)

        # Loop through 1040 times
        for loop_number in range(total_iterations):
            # Construct the command for memory dump
            command = (
                f"sg_raw.exe -o \"{temp_directory}\\memdump_{opcode}_{loop_number:04d}.bin\" "
                f"-r 16128 {drive_letter}: {opcode} {result_array[loop_number]} 00 3F 00 00 "
                f" --timeout=20"
            )
            # Execute the command
            return_code, _, _ = execute_command(command)

            # Update the progress bar
            progress_bar.update(1)

        # Close the progress bar
        progress_bar.close()

        # Combine the binary .bin files in sequential order of loop_number
        combined_file_path = "combined_memdump.bin"
        with open(combined_file_path, "wb") as combined_file:
            for loop_number in range(total_iterations):
                file_path = os.path.join(temp_directory, f"memdump_{opcode}_{loop_number:04d}.bin")

                try:
                    with open(file_path, "rb") as temp_file:
                        combined_file.write(temp_file.read())
                except FileNotFoundError:
                    break

        print(f"\nMemory dump files successfully combined into: {combined_file_path}")

    except SkipException as e:
        print(f"\nSkipping the current operation: {e}")

    finally:
        # Remove the temporary directory and its contents
        shutil.rmtree(temp_directory, ignore_errors=True)

def get_dvd_drive_info(drive_letter):
    wmi = win32com.client.GetObject("winmgmts:")

    # Query the Win32_CDROMDrive class for the specified drive letter
    drives = wmi.ExecQuery(f"SELECT * FROM Win32_CDROMDrive WHERE Drive = '{drive_letter}:'")

    for drive in drives:
        # Retrieve all properties of the DVD drive
        properties = drive.Properties_
        property_names = [prop.Name for prop in properties]
        property_values = drive.Properties_

        # Print the retrieved information
        print(f"\n\n--- DVD Drive Information ({drive_letter}:) ---")

        for name, value in zip(property_names, property_values):
            print(f"{name}: {value}")


def create_new_directory():
    now = datetime.now()
    date_time = now.strftime("%Y-%m-%d %H.%M.%S")
    new_dir = os.path.join(os.getcwd(), date_time)
    
    os.makedirs(new_dir)
    print(f"\nCreated directory: {new_dir}. The .bin dumps, log file, and upload_me.zip will be found there.")
    
    return new_dir


def main():
    start_time = time.time()
    # Start
    print("CD/DVD/BD Drive Memory Dumper")
    print("Version: 2023-12-17")
    print("Author: ehw (Hidden-Palace.org R&D)")
    print("Description: Attempts to create a memory dump using the user specified 3 byte SCSI opcode consisting of 16MB\n") 

    # Ask the user for the drive letter of the drive they want to read from.
    print("Enter the drive letter of your drive: ")
    drive_letter = input()
    
    # Check if the drive the user specified actually exists.
    if dvd_drive_exists(drive_letter):
        print(f"A drive exists at drive letter {drive_letter}.")
    else:
        print(f"No drive or no disc found at drive letter {drive_letter}. Will attempt to dump anyway.")

    # Define a regular expression pattern for the expected format
    opcode_pattern = re.compile(r'^[0-9A-Fa-f]{2} [0-9A-Fa-f]{2} [0-9A-Fa-f]{2}$')

    # Ask the user for the 3 byte opcode of the SCSI command
    print("Enter the SCSI opcode of the command you'd like to try (e.g., 3C 02 00), keep each byte spaced out: ")
    opcode = input()

    # Check if the entered opcode matches the expected format
    if opcode_pattern.match(opcode):
        print("Opcode is in the correct format.")
    else:
        print("Invalid format. Please enter 3 bytes written in hexadecimal spaced out with no spaces before or after.")
        exit

    # Call the function to retrieve drive information
    print("\n---------------------------------------------------------------------------------\n")
    get_dvd_drive_info(drive_letter.upper())

    # Attempt to dump the entire drive's memory, or at least from the beginning of DRAM,  but using the user's specified 3 byte opcode.
    print("\n---------------------------------------------------------------------------------\n")
    mem_dump(opcode, drive_letter)
    print("\n---------------------------------------------------------------------------------\n")
    
   
    # End
    print("\nScript finished!\n")
    # Call the function to create the zip file
    end_time = time.time()
    elapsed_time = end_time - start_time

    # Print script duration.
    print(f"Elapsed time: {elapsed_time} seconds")
    sys.stdout.log.close()
    
    print(f"Zipping files, this might take a while...")
    # Zip the files for submission.
    zip_files()
    
    # Move all the .bin files to a folder named after the current time, this will prevent users from accidentally running the script again and mixing the files up in different runs from different drives.
    current_dir = os.getcwd()
    new_dir = create_new_directory()
    files_to_move = [".bin", "memdump_logfile.log", "upload_me.7z"]

    for file in os.listdir(current_dir):
        if file.endswith(tuple(files_to_move)) and os.path.isfile(file):
            source_path = os.path.join(current_dir, file)
            destination_path = os.path.join(new_dir, file)
            shutil.move(source_path, destination_path)
    
    # Pause the program for user confirmation and review.
    os.system("pause")
    
if __name__ == "__main__":
    main()
