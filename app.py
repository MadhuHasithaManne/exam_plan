from flask import Flask, render_template, request, session, redirect, url_for, send_from_directory,after_this_request
import pandas as pd
import zipfile
import os
import uuid
from flask import Flask, session
from flask import g
from flask_session import Session
import re
import time
import openpyxl 
from datetime import datetime
import tempfile
import shutil
import platform
import subprocess
from flask import Flask, render_template, send_file
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas


app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"  # Stores sessions on disk
Session(app)
app.secret_key = "supersecretkey12345"  # Mandatory for session handling
LATEST_ATTENDANCE_DIR = None
count=0
college_code="H7"
# HEADER_IMAGE_PATH = "E:\paid_projects\exam_seating_system\static\Images\header.jpg"
OUTPUT_DIR = os.path.join(os.getcwd(), 'static', 'output_files')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static", "Images")
HEADER_IMAGE_PATH = os.path.join(STATIC_DIR, "header.jpg")
os.makedirs(OUTPUT_DIR, exist_ok=True)
for foldername, subfolders, filenames in os.walk(BASE_DIR):
        for filename in filenames:
            file_path = os.path.join(foldername, filename)
            print(file_path)
# Pass Python's zip function to Jinja2 templates
app.jinja_env.globals.update(zip=zip)

# Directory for storing temporary files
TEMP_DIR = os.path.join(os.getcwd(), 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

@app.before_request
def make_session_non_permanent():
    session.permanent = False

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            # Input from the user
            num_departments = int(request.form["num_departments"])
            department_names = request.form.getlist("department_names[]")
            subject_codes = request.form.getlist("subject_codes[]")
            subject_names=request.form.getlist("subject_names[]")
            uploaded_file = request.files["roll_numbers_file"]
            date=request.form["date"]
            date=datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
            exam_session=request.form["exam_session"]
            exam_type=request.form["exam_type"]
            room_names = request.form["room_names"].split(',')
            room_names = [room.strip() for room in room_names]
            if uploaded_file.filename == "":
                return "Error: No file uploaded."

            # Load roll numbers and department data
            try:
                df = pd.read_excel(uploaded_file)
                print("File uploaded and read successfully.")
            except Exception as e:
                return f"Error: Unable to read the uploaded file. {str(e)}"

            # Validate input
            if len(department_names) != num_departments or len(subject_codes) != num_departments:
                return "Error: Number of departments or subject codes doesn't match the provided details."

            if not set(department_names).issubset(set(df["Department"].unique())):
                return "Error: Department names do not match with the uploaded file."

            # Map subject codes to departments
            department_subject_map = dict(zip(department_names, subject_codes))
            sub_code_name_map=dict(zip(subject_codes,subject_names))

            # Filter data to include only relevant departments
            df = df[df["Department"].isin(department_names)]

            # Save processed data to a temporary file
            session_id = str(uuid.uuid4())
            temp_file_path = os.path.join(TEMP_DIR, f"{session_id}.csv")
            df.to_csv(temp_file_path, index=False)

            # Save session metadata
            session["session_id"] = session_id
            session["num_departments"] = num_departments
            session["department_subject_map"] = department_subject_map
            session["sub_code_name_map"]=sub_code_name_map
            session["date"]=date
            session["exam_session"]=exam_session
            session["exam_type"]=exam_type
            session["room_names"]=room_names
            session["image"]=HEADER_IMAGE_PATH

            print("Input validation successful and data stored.")
            return render_template("index.html", buttons_visible=True)

        except Exception as e:
            print(f"Error during form submission: {str(e)}")
            return "An error occurred while processing your request. Please try again."

    return render_template("index.html", buttons_visible=False)


def seating_logic():
        session_id = session.get("session_id")
        department_subject_map = session.get("department_subject_map")
        sub_code_name_map=session.get("sub_code_name_map")
        room_names = session.get("room_names")
        if not (session_id and department_subject_map):
            return "Error: Missing data. Please submit the form first."

        temp_file_path = os.path.join(TEMP_DIR, f"{session_id}.csv")
        if not os.path.exists(temp_file_path):
            return "Error: Data file not found. Please submit the form again."
        df = pd.read_csv(temp_file_path)
       
        df.sort_values(by=["Department","Roll Number","Student Name"], inplace=True)
        roll_name_dict = dict(zip(df["Roll Number"], df["Student Name"]))
        g.large_data = roll_name_dict
        department_counts = df["Department"].value_counts().to_dict()
        total_students = df.shape[0]
        print(total_students)
        # Debug print to verify the counts
        print("\n📊 Initial Student Count Per Department:")
        for dept, count in department_counts.items():
            print(f"{dept}: {count} students")

        rooms = []
        special_rooms=[]
        room_number = 1
        session["room_number"]=room_number
        remaining_students = df.copy()
        remaining_departments = df["Department"].unique().tolist()
        available_departments = remaining_departments.copy()
        remaining_students_dict = {
            dept: {"students": [], "subject_code": department_subject_map.get(dept)}
            for dept in remaining_departments
        }
        room_names=room_names
        # Step 1: Assign students to initial rooms
        while len(remaining_students) > 0:
            
            room = {"room_number": room_names[room_number - 1], "side_a": [], "side_b": []}
            side_a, side_b = [], []

            if available_departments:
                dept_a = available_departments[0]
                dept_a_students = remaining_students[remaining_students["Department"] == dept_a]
                subject_code_a = department_subject_map[dept_a]

                if len(dept_a_students) >= 12:
                    while len(side_a) < 24 and not dept_a_students.empty:
                        student = dept_a_students.iloc[0]
                        # side_a.append((student['Department'], student['Roll Number'], subject_code_a))
                        side_a.append((student['Department'],student['Roll Number']))
                        remaining_students = remaining_students[remaining_students["Roll Number"] != student["Roll Number"]]
                        dept_a_students = dept_a_students[dept_a_students["Roll Number"] != student["Roll Number"]]

                    if dept_a_students.empty:
                        available_departments.remove(dept_a)
                else:
                    remaining_students_dict[dept_a]["students"].extend(
                        [(student['Department'], student['Roll Number']) for _, student in dept_a_students.iterrows()]
                    )
                    remaining_students = remaining_students[remaining_students["Department"] != dept_a]
                    available_departments.remove(dept_a)
                    continue  # Skip to the next iteration

            if available_departments:
                for dept_b in available_departments:
                    if department_subject_map[dept_b] != subject_code_a:
                        dept_b_students = remaining_students[remaining_students["Department"] == dept_b]

                        if len(dept_b_students) >= 12:
                            while len(side_b) < 24 and not dept_b_students.empty:
                                student = dept_b_students.iloc[0]
                                #side_b.append((student['Department'], student['Roll Number'], department_subject_map[dept_b]))
                                side_b.append((student['Department'],student['Roll Number']))
                                remaining_students = remaining_students[remaining_students["Roll Number"] != student["Roll Number"]]
                                dept_b_students = dept_b_students[dept_b_students["Roll Number"] != student["Roll Number"]]

                            if dept_b_students.empty:
                                available_departments.remove(dept_b)
                            break
                        else:
                            remaining_students_dict[dept_b]["students"].extend(
                                [(student['Department'], student['Roll Number']) for _, student in dept_b_students.iterrows()]
                            )
                            remaining_students = remaining_students[remaining_students["Department"] != dept_b]
                            available_departments.remove(dept_b)

            while len(side_a) < 24:
                side_a.append(("---"))
            while len(side_b) < 24:
                side_b.append(("---"))

            room["side_a"] = side_a
            room["side_b"] = side_b
            rooms.append(room)
            room_number += 1
        session["room_number"]=room_number
  

        def find_empty_side_for_dept(dept, subject_code):
            """Find an available room where all students of a department can be placed on one side."""
            for room in rooms:
                if all(x[0] == "---" for x in room["side_a"]):  # Check if Side A is empty
                    if not any(student[2] == subject_code for student in room["side_b"] if student[2] is not None):
                        return room, "side_a"

                if all(x[0] == "---" for x in room["side_b"]):  # Check if Side B is empty
                    if not any(student[2] == subject_code for student in room["side_a"] if student[2] is not None):
                        return room, "side_b"

            return None, None

        def assign_students_to_room(room, side, students):
            """Assign students to a room side, ensuring exactly 24 slots are filled."""
            side_students = []

            while len(side_students) < 24 and students:
                side_students.append(students.pop(0)[1])

            while len(side_students) < 24:  # Fill empty slots
                side_students.append(("---"))

            room[side] = side_students


        def create_new_special_room():
            """Create and return a new special room."""
            #ROOM_NAMES = ["CS304A", "CS304B", "CS304C", "CS304D", "CS304E","CS305A", "CS305B", "CS305C", "CS305D", "CS305E","CS306A", "CS306B", "CS306C", "CS306D", "CS306E","CS307A", "CS307B", "CS307C", "CS307D", "CS307E","CS308A", "CS308B", "CS308C", "CS308D", "CS308E"] 
            #room_names = ROOM_NAMES
            room_number=session.get("room_number")

            new_room = {"room_number": room_names[room_number - 1], "side_a": [], "side_b": []}
            room_number += 1 
            
            
            return new_room  # Return the room before adding it to special_rooms


        def assign_unassigned_students():
            """Assign unassigned students while avoiding subject conflicts in special rooms."""
            unassigned_students_list = []
            
            # Collect all unassigned students
            for dept, data in remaining_students_dict.items():
                for student in data["students"]:
                    unassigned_students_list.append((dept, student[1], data["subject_code"]))

            print(f"\n🔎 Total Unassigned Students: {len(unassigned_students_list)}")
            room_number=session.get("room_number")
            # Group by department
            department_groups = {}
            for student in unassigned_students_list:
                dept, roll_number, subject_code = student
                if dept not in department_groups:
                    department_groups[dept] = []
                department_groups[dept].append(student)

            for dept, students in department_groups.items():
                print(f"\n🔹 Assigning Students from Department: {dept}")

                subject_code = students[0][2]  

                # First, check if a normal room is available
                room, side_to_fill = find_empty_side_for_dept(dept, subject_code)

                if room and side_to_fill:
                    print(f"✅ Placing {dept} students in Room {room['room_number']} on {side_to_fill}")
                    assign_students_to_room(room, side_to_fill, students)

                else:
                    # No normal room found → Try placing in an **existing special room sequentially**
                    assigned = False

                    for special_room in special_rooms:
                        # **Fill Side A first (sequentially)**
                        if len(special_room["side_a"]) < 24:
                            print(f"✅ Placing {dept} students in Special Room {special_room['room_number']} on Side A sequentially")
                            
                            while students and len(special_room["side_a"]) < 24:
                                special_room["side_a"].append((students[0][0], students[0][1]))  # Append roll number & subject code
                                students.pop(0)
                            
                            assigned = True

                        # **Once Side A is full, move to Side B (check subject conflicts)**
                        if students and len(special_room["side_b"]) < 24:
                            # Ensure subject code conflict does not happen
                            if not any(student[2] == subject_code for student in special_room["side_a"] if student[2] is not None):
                                print(f"✅ Placing {dept} students in Special Room {special_room['room_number']} on Side B sequentially")

                                while students and len(special_room["side_b"]) < 24:
                                    special_room["side_b"].append(students[0][0], students[0][1])
                                    students.pop(0)

                                assigned = True

                        if assigned:
                            break  # Stop checking once students are placed
                    

                    if not assigned:
                        # **Create new special room only if necessary**
                        print(f"⚠ No available room found. Creating new special room for {dept}.")
                        new_special_room = create_new_special_room()
                        
                        while students and len(new_special_room["side_a"]) < 24:
                            new_special_room["side_a"].append((students[0][0], students[0][1]))
                            students.pop(0)
                        while students and len(new_special_room["side_b"]) < 24:
                            new_special_room["side_b"].append((students[0][0], students[0][1]))
                            students.pop(0)
                        special_rooms.append(new_special_room)
                        print(f"🆕 Special Room {new_special_room['room_number']} created and filled sequentially.")
            for special_room in special_rooms:
                while len(special_room["side_a"]) < 24:
                    special_room["side_a"].append(("---"))

                while len(special_room["side_b"]) < 24:
                    special_room["side_b"].append(("---"))

            print("✅ All special rooms are now completely filled with placeholders where necessary.")

        assign_unassigned_students()
        rooms.extend(special_rooms)
        return rooms,remaining_departments


@app.route("/seating_plan")
def seating_plan():
    date=session.get("date")
    exam_type=session.get("exam_type")
    college_code="H7"

   
    try:
        # Retrieve session metadata
        rooms,remaining_departments=seating_logic()
        
        return render_template(
            
        "result.html",date=date,exam_type=exam_type,college_code=college_code,rooms=rooms)

    except Exception as e:
        return f"An error occurred: {str(e)}"
    


@app.route("/generate_attendance_sheets")
def generate_attendance_sheets():
    try:
        def force_delete_directory(directory):
            """Tries to delete a directory, retrying if files are locked."""
            if os.path.exists(directory):
                for _ in range(5):  # Try up to 5 times
                    try:
                        shutil.rmtree(directory)  # Attempt to delete
                        break  # Exit loop if successful
                    except PermissionError:
                        print(f"⚠️ Directory {directory} is in use, retrying...")
                        time.sleep(2)  # Wait before retrying

        # ✅ Ensure Excel processes are terminated before deletion
        os.system("taskkill /F /IM excel.exe >nul 2>&1")

        # ✅ Force delete the directory before recreating it
        force_delete_directory(OUTPUT_DIR)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        rooms,remaining_departments=seating_logic()
        date=session.get("date")
        exam_type=session.get("exam_type")
        exam_session=session.get("exam_session")
        department_subject_map = session.get("department_subject_map")
        image=session.get("image")
        sub_code_name_map=session.get("sub_code_name_map")
        roll_name_dict = getattr(g, "large_data", {})
        output_dir = os.path.join(OUTPUT_DIR, "attendance_sheets")
        os.makedirs(output_dir, exist_ok=True)
        for room in rooms:
            room_file_path = os.path.join(output_dir, f"room_{room['room_number']}_attendance.xlsx")
            with pd.ExcelWriter(room_file_path, engine='xlsxwriter', mode='w') as writer:
                for department in remaining_departments:
                    # Filter students for this department in the current room
                    subject_code = department_subject_map.get(department, "Not Available")
                    subject_name = sub_code_name_map.get(subject_code, "Not Available")
                    roll_numbers = [student[1] for student in room["side_a"] if student[0] == department] + \
                                [student[1] for student in room["side_b"] if student[0] == department]
                    
                    if not roll_numbers:  
                        continue
                    student_names = [roll_name_dict.get(roll, "Not Found") for roll in roll_numbers]
                    dept_df = pd.DataFrame({
                        "Roll Number": roll_numbers,
                        "Names":student_names,
                        "Signature": [""] * len(roll_numbers),
                        "Booklet Number": [""] * len(roll_numbers)  
                    })

                    # Sheet name must be max 31 characters
                    sheet_name = f"{department}_Room{room['room_number']}"[:31]  

                    dept_df.to_excel(writer, index=False, sheet_name=sheet_name, startrow=10)

                    workbook = writer.book
                    worksheet = writer.sheets[sheet_name]
                    for row in range(4):  
                        worksheet.set_row(row, 20) 
                    worksheet.insert_image('A1', image, {
                    'x_scale': 0.5,  # Adjust width scale to fit A1:D4
                    'y_scale': 0.3,  # Adjust height scale to fit A1:A4
                    'object_position': 1  # Ensures it moves with cells but does not resize beyond them
                })

                    # Nominal Roll Title (Centered below header)
                    nominal_roll_format = workbook.add_format({'bold': True, 'underline': True, 'font_size': 12, 'align': 'center'})
                    worksheet.merge_range('A6:E6', "NOMINAL ROLL'S", nominal_roll_format)

                   
                    left_format = workbook.add_format({'bold': True, 'font_size': 12, 'align': 'left'})  # Changed to Right
                    right_format = workbook.add_format({'bold': True, 'font_size': 12, 'align': 'left'})  # Changed to Left

                    
                    worksheet.write('E7', f"Date: {date}", right_format)

                    worksheet.write('E8', f"Session: {exam_session}", right_format)

                    worksheet.write('E9', f"Department:{department}", right_format)

                    worksheet.merge_range('A7:D7',f"Name of Exam: {exam_type}", left_format)
                    worksheet.merge_range('A8:C8', f"Course Code & Name: {subject_code} - {subject_name}", left_format)

                    worksheet.merge_range('A9:B9', f"Room:{room['room_number']}", left_format)


                    # Column Formatting
                    worksheet.set_column('A:A', 10)  # Sno column width
                    worksheet.set_column('B:B', 20)  # Roll Number column width
                    worksheet.set_column('C:C', 35)  # Names column width
                    worksheet.set_column('D:D', 20)  # Booklet Number column width
                    worksheet.set_column('E:E', 25)  # Signature column width

                    # Header Formatting
                    header_format = workbook.add_format({
                        'bold': True, 
                        'align': 'center', 
                        'border': 1, 
                        'bg_color': '#f2f2f2'
                    })
                    

                    # Write Table Headers Correctly
                    worksheet.write(10, 0, "Sno", header_format)
                    worksheet.write(10, 1, "Roll Number", header_format) 
                    worksheet.write(10, 2, "Names",header_format)  
                    worksheet.write(10, 3, "Booklet Number", header_format)  
                    worksheet.write(10, 4, "Signature", header_format)   

                    # Border Formatting for Data
                    border_format = workbook.add_format({'border': 1, 'align': 'center'})
                    bor_format= workbook.add_format({'border': 1, 'align': 'left'})

                   
                    for row_idx in range(len(roll_numbers)):
                        worksheet.write(row_idx + 11, 0, row_idx + 1, border_format)  # Serial number
                        worksheet.write(row_idx + 11, 1, roll_numbers[row_idx], border_format)  # Roll Number
                        worksheet.write(row_idx + 11, 2, student_names[row_idx], bor_format)  # Name column
                        worksheet.write(row_idx + 11, 3, "", border_format)  # Booklet Number column
                        worksheet.write(row_idx + 11, 4, "", border_format)  # Signature column

                    # Set row height for better visibility
                    for row_idx in range(10, len(roll_numbers) + 12):
                        worksheet.set_row(row_idx, 21.5)

                    # Page margins
                    worksheet.set_margins(left=0.75, right=0.75, top=0.75, bottom=0.75)
                    

                    
                    footer_start_row = len(roll_numbers) + 13  # Position footer below student list

                    # Format for Footer Titles
                    footer_title_format = workbook.add_format({
                        'bold': True, 
                        'align': 'center', 
                        'border': 1, 
                        'bg_color': '#f2f2f2'
                    })

                    # Format for Footer Data (Values)
                    footer_data_format = workbook.add_format({
                        'align': 'center'
                    })


                    worksheet.merge_range(footer_start_row, 0, footer_start_row, 1, f"Registered: {len(roll_numbers)}", footer_title_format)

                    
                    worksheet.write(footer_start_row, 2, f"Absent:", footer_title_format)

                    
                    worksheet.merge_range(footer_start_row, 3, footer_start_row, 4, f"Present:   ", footer_title_format)

                    
                    signature_start_row = footer_start_row + 6

                   
                    worksheet.merge_range(signature_start_row, 0, signature_start_row, 1, "Examiner 1", footer_data_format)
                    worksheet.write(signature_start_row, 2,"Examiner 2", footer_data_format)
                    worksheet.merge_range(signature_start_row, 3, signature_start_row, 4, "Chief Superintendent", footer_data_format)

                   
                    worksheet.set_row(signature_start_row, 25)  # Enough space for signatures
            

        zip_filename = os.path.join(output_dir, "attendance_sheets.zip")
        count=0
        with zipfile.ZipFile(zip_filename, 'w') as zipf:
            for room in rooms:
                count+=1
                room_file_path = os.path.join(output_dir, f"room_{room['room_number']}_attendance.xlsx")
                zipf.write(room_file_path, os.path.basename(room_file_path))
        print(f"All attendance sheets have been zipped: {zip_filename}")


        # zip_file_path = os.path.join(output_dir, "attendance_sheets.zip")  # ZIP file path
        # extract_dir = os.path.join(output_dir, "extracted_excels")  # Folder for extracted Excel files
        # pdf_output_dir = os.path.join(output_dir, "pdfs")  # Folder for generated PDFs
        # pdf_zip_path = os.path.join(output_dir, "converted_pdfs.zip")  # Final ZIP file for PDFs

        # # Ensure necessary directories exist
        # os.makedirs(extract_dir, exist_ok=True)
        # os.makedirs(pdf_output_dir, exist_ok=True)

        # # Step 1: Extract ZIP file
        # with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        #     zip_ref.extractall(extract_dir)

    
        # pythoncom.CoInitialize()
        # excel = win32com.client.Dispatch("Excel.Application")
        # excel.Visible = False  # Keep Excel hidden
        # excel.DisplayAlerts = False  # Prevent pop-ups
        # excel.ScreenUpdating = False

        # for filename in os.listdir(extract_dir):
        #     if filename.endswith(".xlsx") or filename.endswith(".xls"):
        #         excel_path = os.path.join(extract_dir, filename)

        #         # Open the workbook
        #         try:
        #             workbook = excel.Workbooks.Open(excel_path)
        #             if workbook is None:
        #                 print(f"Skipping {filename}, could not open.")
        #                 continue  # Skip if workbook is invalid

        #             # Convert each sheet to a separate PDF
        #             for sheet in workbook.Sheets:
        #                 pdf_path = os.path.join(pdf_output_dir, f"{filename.replace('.xlsx', '').replace('.xls', '')}_{sheet.Name}.pdf")
                        
        #                 # Set page to fit A4
        #                 sheet.PageSetup.Zoom = False  # Disable zoom
        #                 sheet.PageSetup.FitToPagesWide = 1  # Fit width to one page
        #                 sheet.PageSetup.FitToPagesTall = 1  # Fit height to one page
        #                 sheet.PageSetup.Orientation = 1  # Landscape (1 for Portrait)
                        
        #                 # Export as PDF
        #                 sheet.ExportAsFixedFormat(0, pdf_path)

        #             workbook.Close(False) 

        #         except Exception as e:
        #             print(f"Error processing {filename}: {e}")

        # # Quit Excel application
        # excel.Quit()
        # pythoncom.CoUninitialize()

        # # Step 4: Zip all PDFs
        # with zipfile.ZipFile(pdf_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        #     for pdf_file in os.listdir(pdf_output_dir):
        #         pdf_path = os.path.join(pdf_output_dir, pdf_file)
        #         zipf.write(pdf_path, os.path.basename(pdf_path))

        # # Optional: Clean up extracted Excel files
        # shutil.rmtree(extract_dir)
        # shutil.rmtree(pdf_output_dir)
        
        def set_excel_page_setup(input_path):
            """Modifies Excel page setup to ensure it fits on one page before PDF conversion."""
            try:
                wb = openpyxl.load_workbook(input_path)
                for sheet in wb.worksheets:
                    ws = sheet.page_setup
                    ws.fitToPage = True  # ✅ Ensure content fits to one page
                    ws.fitToHeight = 1
                    ws.fitToWidth = 1
                wb.save(input_path)  # ✅ Overwrite Excel file with new settings
                print(f"✔️ Page settings updated for: {input_path}")
            except Exception as e:
                print(f"⚠️ Error updating page settings: {e}")
        def convert_excel_to_pdf(input_path, output_dir):
            """Converts an Excel file to PDF while ensuring A4 page setup. Works on Windows, Linux & macOS."""
            
            filename = os.path.splitext(os.path.basename(input_path))[0]  # Remove extension
            pdf_path = os.path.join(output_dir, f"{filename}.pdf")  # Output PDF path

            try:
                set_excel_page_setup(input_path)

        # ✅ Convert Excel to PDF using LibreOffice
                subprocess.run([
                    "soffice", "--headless", "--convert-to", "pdf", "--outdir",
                    output_dir, input_path
                ], check=True)
                print(f"✅ Converted {input_path} -> {pdf_path}")

            except subprocess.CalledProcessError as e:
                print(f"❌ Conversion failed for {input_path}: {e}")

        # ✅ Define Paths
        zip_file_path = os.path.join(output_dir, "attendance_sheets.zip")  # ZIP file path
        extract_dir = os.path.join(output_dir, "extracted_excels")  # Extracted Excel files
        pdf_output_dir = os.path.join(output_dir, "pdfs")  # PDFs folder
        pdf_zip_path = os.path.join(output_dir, "converted_pdfs.zip")  # Final ZIP file for PDFs

        # ✅ Ensure necessary directories exist
        os.makedirs(extract_dir, exist_ok=True)
        os.makedirs(pdf_output_dir, exist_ok=True)

        # ✅ Step 1: Extract ZIP file
        with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        # ✅ Step 2: Convert each Excel file to PDF
        for filename in os.listdir(extract_dir):
            if filename.endswith(".xlsx") or filename.endswith(".xls"):
                excel_path = os.path.join(extract_dir, filename)
                convert_excel_to_pdf(excel_path, pdf_output_dir)

        # ✅ Step 3: Zip all PDFs
        with zipfile.ZipFile(pdf_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for pdf_file in os.listdir(pdf_output_dir):
                pdf_path = os.path.join(pdf_output_dir, pdf_file)
                zipf.write(pdf_path, os.path.basename(pdf_path))

        # ✅ Step 4: Clean up extracted Excel files
        shutil.rmtree(extract_dir)
        shutil.rmtree(pdf_output_dir)



        print(f"All Excel sheets converted to PDFs and saved in: {pdf_zip_path}")
        session['LATEST_ATTENDANCE_DIR']=output_dir
        session['count']=count
        return render_template("download_redirect.html")

    except Exception as e:
        print(f"Error during attendance sheet generation: {str(e)}")
        return "An error occurred while generating the attendance sheets. Please try again."

@app.route("/download_attendance")
def download_attendance():

    #output_dir = os.path.join(OUTPUT_DIR, "attendance_sheets")
    #return send_from_directory(output_dir, "converted_pdfs.zip", as_attachment=True)
    output_dir = session.get('LATEST_ATTENDANCE_DIR', OUTPUT_DIR)
    pdf_zip_path = os.path.join(output_dir, "converted_pdfs.zip")

    if not os.path.exists(pdf_zip_path):
        return "Error: File not found."
    return send_from_directory(output_dir, "converted_pdfs.zip", as_attachment=True)


def get_seating_plan():
    LATEST_ATTENDANCE_DIR=session.get('LATEST_ATTENDANCE_DIR')
    count=session.get('count')
    date=session.get("date")
    exam_session=session.get("exam_session")
    room_names=session.get("room_names")
    department_subject_map = session.get("department_subject_map")
    image=session.get("image")
    sub_code_name_map=session.get("sub_code_name_map")
    if not LATEST_ATTENDANCE_DIR:
        print("Error: No latest attendance sheet directory found.")
        return {}

    directory = LATEST_ATTENDANCE_DIR
    seating_plan = {} # dept wise plans to keep in wtsap
    room_plan={} #Noticeboard plan
    dept_plan={} #dept and room plan 

    for filename in os.listdir(directory):
        l=filename.split("_")
        if filename.endswith(".xlsx") and filename.startswith("room_"):
            match = re.search(r"room_([A-Za-z]*\d+[A-Za-z]*)", filename)
            if not match:
                continue  
            room_name = match.group(1) 
            file_path = os.path.join(directory, filename)

            try:
                xls = pd.ExcelFile(file_path)
                for sheet_name in xls.sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                    if df.shape[0] < 11:
                        continue

                        
                    department = sheet_name.split("_")[0]
                    subject_code = department_subject_map.get(department, "Not Available")
                    subject_name = sub_code_name_map.get(subject_code, "Not Available")
    
                    df = pd.read_excel(xls, sheet_name=sheet_name, skiprows=10)

                    if "Roll Number" not in df.columns:
                        continue

                    if not df.empty:
                        first_roll = df["Roll Number"].dropna().astype(str).min()
                        last_roll = df["Roll Number"].dropna().astype(str).max()

                        if department not in seating_plan:
                            seating_plan[department] = { "rooms": []}
                        if room_name not in dept_plan:
                            dept_plan[room_name] = []

                        # ✅ Add department-wise roll range inside the room
                        dept_plan[room_name].append({
                            "Department": department,
                            "Subject Code": subject_code,
                            "Subject Name": subject_name,
                            "From": first_roll,
                            "To": last_roll
                        })

                        roll_range = f"{first_roll}-{last_roll}"
                        
                        if room_name in room_plan:
                            room_plan[room_name].append(roll_range)
                        else:
                            room_plan[room_name] = [roll_range]
                            
                        seating_plan[department]["rooms"].append({
                                "Room": room_name,
                                "subject_code":subject_code,
                                "subject_name":subject_name,
                                "First Roll": f"({first_roll})",
                                "Last Roll": f"({last_roll})"
                        })
            except Exception as e:
                print(f"Error processing file {filename}: {e}")

    return seating_plan,room_plan,dept_plan
@app.route("/download_pdf")
def download_pdf():
    try:
        date = session.get("date")
        exam_session = session.get("exam_session")
        image = session.get("image")
        seating_plan, room_plan, dept_plan = get_seating_plan()

        if not seating_plan:
            return "Error: Seating plan could not be generated.", 500

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=60)
        elements = []
        styles = getSampleStyleSheet()

        normal_style = styles["Normal"]  # ✅ Default font
        heading_style = styles["Heading3"]  # ✅ Default heading font

        for department, details in seating_plan.items():
            rooms = details["rooms"]
            subject_code = set(room["subject_code"] for room in rooms)
            subject_name = set(room["subject_name"] for room in rooms)
            subject_codes_str = ", ".join(subject_code) if subject_code else "Not Available"
            subject_names_str = ", ".join(subject_name) if subject_name else "Not Available"

            header_img = Image(image, width=500, height=120)  
            elements.append(header_img)
            
            left_details = Paragraph(f"<b>Department:</b> {department}<br/><b>Subject:</b> {subject_names_str}<br/><b>Code:</b> {subject_codes_str}", normal_style)
            right_details = Paragraph(f"<b>Date:</b> {date}<br/><b>Session:</b> {exam_session}", normal_style)

            details_table = Table([[left_details, right_details]], colWidths=[300, 130])

            details_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))

            elements.append(details_table)
            elements.append(Spacer(1, 0.2 * inch))

            data = [["Room Number", "FROM", "TO"]]

            for room in sorted(rooms, key=lambda x: x["Room"]):
                data.append([room["Room"], room["First Roll"], room["Last Roll"]])

            table = Table(data, colWidths=[150, 150, 150])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]))

            elements.append(table)
            elements.append(PageBreak())

        if not elements:
            return "Error: No data available for the PDF.", 500

        doc.build(elements)
        buffer.seek(0)

        print("✅ PDF successfully generated!")

        return send_file(
            buffer,
            as_attachment=True,
            download_name="Seating_Plan.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:
        print(f"❌ Error generating PDF: {e}")
        return "Error generating PDF.", 500


# def download_pdf():
#     try:
#         if os.path.exists("calibri.ttf"):
#             font_path = "calibri.ttf"
#         elif os.path.exists("/usr/share/fonts/truetype/calibri.ttf"):
#             font_path = "/usr/share/fonts/truetype/calibri.ttf"
#         date=session.get("date")
#         exam_session=session.get("exam_session")
#         image=session.get("image")
#         seating_plan, room_plan,dept_plan = get_seating_plan()
#         if not seating_plan:
#             return "Error: Seating plan could not be generated.", 500
#         pdfmetrics.registerFont(TTFont("Calibri", font_path))  # Use "times.ttf" if available
#         #pdfmetrics.registerFont(TTFont('Calibri', '/usr/share/fonts/truetype/calibri.ttf'))
#         # **Create Custom Styles with Times New Roman**
#         styles = getSampleStyleSheet()
#         times_normal = ParagraphStyle(
#             "CalibriNormal",
#             parent=styles["Normal"],
#             fontName="Calibri",
#             fontSize=12
#         )

#         times_heading = ParagraphStyle(
#             "CalibriNormal",
#             parent=styles["Heading3"],
#             fontName="Calibri",
#             fontSize=14,
#             spaceAfter=10
#         )
#         buffer = BytesIO()
#         doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=60)
#         elements = []
#         styles = getSampleStyleSheet()
        

#         for department, details in seating_plan.items():
#             rooms = details["rooms"]  # ✅ Extract room details
#             subject_code = set(room["subject_code"] for room in rooms)
#             subject_name = set(room["subject_name"] for room in rooms)
#             subject_codes_str = ", ".join(subject_code) if subject_code else "Not Available"
#             subject_names_str = ", ".join(subject_name) if subject_name else "Not Available"
#             header_img = Image(image, width=500, height=120)  
#             elements.append(header_img)
            
#             left_details = Paragraph(f"<b>Department:</b> {department}<br/><b>Subject:</b> {subject_names_str}<br/><b>Code:</b> {subject_codes_str}", times_normal)
#             right_details = Paragraph(f"<b>Date:</b> {date}<br/><b>Session:</b> {exam_session}", times_normal)

#             # ✅ Create a two-column table for details
#             details_table = Table([[left_details, right_details]], colWidths=[300, 130])  # Adjust width as needed

#             # ✅ Apply styles
#             details_table.setStyle(TableStyle([
#                 ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Left details aligned left
#                 ('ALIGN', (1, 0), (1, -1), 'RIGHT'),  # Right details aligned right
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Align text to top
#                 ('BOTTOMPADDING', (0, 0), (-1, -1), 5),  # Padding
#             ]))

#             # ✅ Add to elements
#             elements.append(details_table)
#             elements.append(Spacer(1, 0.2 * inch))


#             data = [["Room Number", "FROM", "TO"]]

#             for room in sorted(rooms, key=lambda x: x["Room"]):
#                 data.append([room["Room"], room["First Roll"], room["Last Roll"]])

#             table = Table(data, colWidths=[150, 150, 150])
#             table.setStyle(TableStyle([
#                 ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
#                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
#                 ("ALIGN", (0, 0), (-1, -1), "CENTER"),
#                 ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
#                 ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
#                 ("GRID", (0, 0), (-1, -1), 1, colors.black),
#             ]))

#             elements.append(table)
#             elements.append(PageBreak())

#         if not elements:
#             return "Error: No data available for the PDF.", 500

#         doc.build(elements)
#         buffer.seek(0)  # Reset buffer

#         print("✅ PDF successfully generated!")

#         return send_file(
#             buffer,
#             as_attachment=True,
#             download_name="Seating_Plan.pdf",
#             mimetype="application/pdf"
#         )

#     except Exception as e:
#         print(f"❌ Error generating PDF: {e}")
#         return "Error generating PDF.", 500
    
@app.route("/download_room_pdf")
def download_room_pdf():
    try:
        date=session.get("date")
        exam_session=session.get("exam_session")
        image=session.get("image")

        # **Create Custom Styles with Times New Roman**
        styles = getSampleStyleSheet()
        
        seating_plan, room_plan,dept_plan = get_seating_plan()
        if not room_plan:
            return "Error: Seating plan could not be generated.", 500

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=60)
        elements = []

        # Styles
        styles = getSampleStyleSheet()
      
        normal_style = styles["Normal"]  # ✅ Default font
        heading_style = styles["Heading3"]  
        header_img = Image(image, width=500, height=120)  
        elements.append(header_img)

        date_paragraph = Paragraph(f"<b>Date:</b> {date}", normal_style)  
        session_paragraph = Paragraph(f"<b>Session:</b> {exam_session}", normal_style)

        # ✅ Create a Two-Column Table for Alignment
        date_session_table = Table([[date_paragraph, session_paragraph]], colWidths=[250, 150])  # Adjust column width

        # ✅ Apply Styling
        date_session_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Align Date to Left
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),  # Align Session to Right
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Align text to top
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),  # Add padding
        ]))

        # ✅ Add to Elements
        elements.append(date_session_table)
        elements.append(Spacer(1, 0.2 * inch)) 

        # Add Space
        elements.append(Paragraph("<br/><br/>", normal_style))

        # Table Headers (First Roll Numbers, then Room Name)
        data = [["Roll Numbers", "Room Name"]]

        # Convert dictionary to table format (Swap columns)
        for room, roll_ranges in room_plan.items():
            roll_text = ", ".join(roll_ranges)  # Convert list to a string
            data.append([Paragraph(roll_text, normal_style), room])  # Wrap text in a Paragraph

        # Create Table with Auto-Adjusting Row Heights
        table = Table(data, colWidths=[300, 150])  # Wider column for Roll Numbers
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),  # Align text in the middle
        ]))

        elements.append(table)

        # Build PDF
        doc.build(elements)
        print("✅ Room-Wise Seating Plan PDF Generated")

        buffer.seek(0)  # Reset buffer

        return send_file(
            buffer,
            as_attachment=True,
            download_name="Room_Plan.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:
        print(f"❌ Error generating PDF: {e}")
        return "Error generating PDF.", 500


@app.route("/dept_room_pdf")
def dept_room_pdf():
    try:
        date = session.get("date")
        exam_session = session.get("exam_session")
        image=session.get("image")
        print(image)
        # ✅ Register Calibri Font

        # ✅ Define Styles
        styles = getSampleStyleSheet()
        normal_style = styles["Normal"]  # ✅ Default font
        heading_style = styles["Heading3"]  

        # ✅ Fetch the room-wise plan
        seating_plan, room_plan, dept_plan = get_seating_plan()
        print("first",dept_plan)
        if not dept_plan:
            return "Error: Seating plan could not be generated.", 500

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=60)
        elements = []

        # ✅ Process Each Room Separately
        for room, depts in dept_plan.items():
            # ✅ Add Header Image (if exists)
            header_img = Image(image, width=500, height=120)  
            elements.append(header_img)

            # ✅ Create Date & Session Table (Aligned Left & Right)
            date_session_table = Table(
                [[Paragraph(f"<b>Date:</b> {date}", normal_style)], 
                [Paragraph(f"<b>Session:</b> {exam_session}", normal_style)]], 
                colWidths=[400]  # Adjust width as needed
            )

            date_session_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),  # Align all text to the right
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),   # Align text to top
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))

            elements.append(date_session_table)
            elements.append(Spacer(1, 0.2 * inch))  

            # ✅ Room Title
            elements.append(Paragraph(f"<b>Room: {room}</b>", heading_style))
            elements.append(Spacer(1, 0.1 * inch))

            # ✅ Table Headers
            data = [["Department", "From", "To"]]

            # ✅ Add Department Data for the Room
            for dept in depts:
                department_name = dept["Department"]
                from_roll = dept["From"]
                to_roll = dept["To"]

                data.append([
                    Paragraph(department_name, normal_style), 
                    Paragraph(from_roll, normal_style), 
                    Paragraph(to_roll, normal_style)
                ])

            # ✅ Create Table with Auto-Adjusting Row Heights
            table = Table(data, colWidths=[150, 150, 150])  # Adjust column widths as needed
            table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 1, colors.black),  # Add borders
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),  # Center-align header
                ("ALIGN", (0, 1), (-1, -1), "CENTER"),  # Center-align all data
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),  # Header background
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),  # Header text color
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),  # Align text in the middle
            ]))

            elements.append(table)

            # ✅ Add a Page Break After Each Room
            elements.append(PageBreak())

        # ✅ Build PDF
        doc.build(elements)
        print("✅ Room-Wise Department Plan PDF Generated")
        print("1234")
        
        print("departments",dept_plan)
        buffer.seek(0)  # Reset buffer
        print("📂 Sending PDF File to Client...")
        return send_file(
            buffer,
            as_attachment=True,  # Forces download
            download_name="Department_Plan.pdf",
            mimetype="application/pdf",
            etag=False,  # Disable caching issues
            cache_timeout=0,  # Avoid cached responses
            last_modified=None
        )


    except Exception as e:
        print(f"❌ Error generating PDF: {e}")
        return "Error generating PDF.", 500




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=True)
