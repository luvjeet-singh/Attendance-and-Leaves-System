from enum import Enum
from io import BytesIO
import os
from fastapi import FastAPI, File, Form, Query, Response, UploadFile, HTTPException, responses
from typing import Optional
from fastapi.responses import FileResponse, StreamingResponse
import mysql.connector
from fastapi.staticfiles import StaticFiles
import pandas as pd
from passlib.context import CryptContext
from pydantic import BaseModel
from datetime import datetime
import xlsxwriter
from tempfile import NamedTemporaryFile

app = FastAPI()

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

mydb = mysql.connector.connect(
    host="127.0.0.1",
    user="root",
    password="Khalsa",
    database="luv_attendance"
)

@app.post("/employee/")
def add_employee(
    name: str,
    email: str,
    password: str,
    gender: str,
    emp_id: int
):
    # Hash the password before storing it in the database
    hashed_password = pwd_context.hash(password)

    cursor = mydb.cursor()
    sql = "INSERT INTO employee (name, email, hashed_password, gender, emp_id) VALUES (%s, %s, %s, %s, %s)"
    val = (name, email, hashed_password, gender, emp_id)
    cursor.execute(sql, val)
    mydb.commit()
    return {"message": "Employee added successfully"}

@app.post("/login/")
def login(email: str, password: str):
    cursor = mydb.cursor()
    sql = "SELECT hashed_password FROM employee WHERE email = %s"
    cursor.execute(sql, (email,))
    result = cursor.fetchone()

    if result:
        hashed_password = result[0]
        # Verify provided password against hashed password
        if pwd_context.verify(password, hashed_password):
            return {"message": "Login successful"}
        else:
            return {"message": "Invalid email or password"}
    else:
        return {"message": "Invalid email or password"}

uploads_dir = "uploads"
os.makedirs(uploads_dir, exist_ok=True)  

@app.post("/attendance1/")
async def add_attendance(
    Name: str = Form(...),
    Time: str = Form(...),
    emp_id: int = Form(...),
    image: UploadFile = File(...)
):
    try:
        cursor = mydb.cursor()

        # Save the image to the uploads folder
        image_path = os.path.join(uploads_dir, image.filename)
        with open(image_path, "wb") as f:
            f.write(image.file.read())

        # Construct full URL of the image
        image_url = f"http://127.0.0.1:8000/{uploads_dir}/{image.filename}"

        # Fetch the current date and time
        current_datetime = datetime.now()

        # Format the date as needed (in YYYY-MM-DD format)
        Date = current_datetime.strftime("%Y-%m-%d")

        # Calculate day based on the current date
        day = current_datetime.strftime("%A")


        # Convert time string to datetime object
        attendance_time = datetime.strptime(Time, "%H:%M:%S")

        # Check if InTime is provided
        cursor.execute("SELECT * FROM attendance WHERE Date = %s AND emp_id = %s", (Date, emp_id))
        existing_attendance = cursor.fetchone()  # Consume all results

        if existing_attendance:
            # If an attendance record exists for the given date and emp_id
            # then update the OutTime and WorkingHours
            out_time = attendance_time
            in_time = existing_attendance[4]  # Fetch existing InTime from the first row
            time_difference = str(out_time - in_time)
            # Split the string by space
            time_parts = time_difference.split(" ")
            # Take the second part which is the time
            time_only = time_parts[1]
            working_hours = time_only # Convert timedelta to string

            # Update the existing attendance record in the database
            sql = "UPDATE attendance SET OutTime = %s, WorkingHours = %s WHERE Date = %s AND emp_id = %s"
            val = (out_time, working_hours, Date, emp_id)
            cursor.execute(sql, val)

        else:
            # If it's the first attendance record for the given date and emp_id
            # then update the InTime and leave OutTime and WorkingHours as NULL
            in_time = attendance_time
            out_time = None
            working_hours = None

            # Insert or update the attendance record in the database
            sql = "INSERT INTO attendance (Name, Date, day, InTime, OutTime, WorkingHours, emp_id, image_url) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            val = (Name, Date, day, in_time, out_time, working_hours, emp_id, image_url)

        
        
        cursor.execute(sql, val)
        mydb.commit()

        return {"message": "Attendance added successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/attendance2/")
def get_attendance(month: int, year: int, Name: str):
    cursor = None  # Initialize cursor variable
    try:
        # Create cursor to execute SQL queries
        cursor = mydb.cursor(dictionary=True)
        
        # Query to fetch attendance based on month, year, and employee name
        sql = "SELECT * FROM attendance WHERE MONTH(Date) = %s AND YEAR(Date) = %s AND Name = %s"
        val = (month, year, Name)
        
        # Execute the SQL query
        cursor.execute(sql, val)
        
        # Fetch all the attendance records
        attendance_records = cursor.fetchall()
        
        if not attendance_records:
            # If no attendance records found, raise HTTPException with 404 status code
            raise HTTPException(status_code=404, detail="No attendance records found")
        
        return {"attendance": attendance_records}
    
    except mysql.connector.Error as err:
        # If any error occurs during database operation, raise HTTPException with 500 status code
        raise HTTPException(status_code=500, detail=f"Database error: {err}")

    finally:
        # Close the cursor and database connection
        if cursor is not None:
            cursor.close()
        mydb.close()

@app.get("/attendance3")
def get_attendance3(Date: str):
    cursor = None
    try:
        cursor = mydb.cursor(dictionary=True)

        sql = "SELECT * FROM attendance WHERE Date = %s"
        val = (Date,)
        cursor.execute(sql, val)

        attendance_records = cursor.fetchall()
        
        if not attendance_records:
            # If no attendance records found, raise HTTPException with 404 status code
            raise HTTPException(status_code=404, detail="No attendance records found")
        
        return {"attendance": attendance_records}
    
    except mysql.connector.Error as err:
        # If any error occurs during database operation, raise HTTPException with 500 status code
        raise HTTPException(status_code=500, detail=f"Database error: {err}")

    finally:
        # Close the cursor and database connection
        if cursor is not None:
            cursor.close()
        mydb.close()

@app.put("/attendance4/{Date}/{id}/")
def edit_attendance(
    Date: str,
    id: int,
    Name: Optional[str] = None,
    InTime: Optional[str] = None,
    OutTime: Optional[str] = None
):
    try:
        # Create cursor to execute SQL queries
        cursor = mydb.cursor(dictionary=True)

        # Check if any field to be updated is provided
        if Name is None and InTime is None and OutTime is None:
            raise HTTPException(status_code=400, detail="No fields to update provided")

        # Construct SQL UPDATE query based on provided fields
        sql = "UPDATE attendance SET "
        updates = []

        if Name is not None:
            updates.append("Name = %s, ")
        if InTime is not None:
            updates.append("InTime = %s, ")
        if OutTime is not None:
            updates.append("OutTime = %s, ")

        sql += "".join(updates)
        sql = sql.rstrip(', ')  # Remove the trailing comma
        sql += " WHERE Date = %s AND id = %s"

        # Construct the values list dynamically based on the provided fields
        values = []
        if Name is not None:
            values.append(Name)
        if InTime is not None:
            values.append(InTime)
        if OutTime is not None:
            values.append(OutTime)
        values.extend([Date, id])

        # Execute the SQL query to update attendance
        cursor.execute(sql, values)
        mydb.commit()

        # Check if any rows were affected by the update
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Attendance record not found")

        return {"message": "Attendance updated successfully"}

    except mysql.connector.Error as err:
        # If any error occurs during database operation, raise HTTPException with 500 status code
        raise HTTPException(status_code=500, detail=f"Database error: {err}")

    finally:
        # Close the cursor and database connection
        if cursor is not None:
            cursor.close()
        mydb.close()

@app.delete("/attendance5/{id}/")
def delete_attendance(id: int):
    try:
        # Create cursor to execute SQL queries
        cursor = mydb.cursor()

        # SQL query to delete attendance record with the provided ID
        sql = "DELETE FROM attendance WHERE id = %s"

        # Execute the SQL query with the provided ID
        cursor.execute(sql, (id,))
        mydb.commit()

        # Check if any rows were affected by the delete operation
        if cursor.rowcount == 0:
            # If no rows were affected, raise HTTPException with 404 status code
            raise HTTPException(status_code=404, detail="Attendance record not found")

        return {"message": "Attendance record deleted successfully"}

    except mysql.connector.Error as err:
        # If any error occurs during database operation, raise HTTPException with 500 status code
        raise HTTPException(status_code=500, detail=f"Database error: {err}")

    finally:
        # Close the cursor and database connection
        if cursor is not None:
            cursor.close()
        mydb.close()

@app.get("/attendance_count/")
def get_attendance_count(month: int, year: int):
    try:
        # Create cursor to execute SQL queries
        cursor = mydb.cursor(dictionary=True)

        # Construct SQL query to get attendance count for each employee by name
        sql = """
            SELECT Name, COUNT(*) as AttendanceCount
            FROM attendance
            WHERE MONTH(Date) = %s AND YEAR(Date) = %s
            GROUP BY Name
        """

        # Execute the SQL query with the provided month and year
        cursor.execute(sql, (month, year))

        # Fetch all rows as dictionaries
        attendance_counts = cursor.fetchall()

        # If no records found, return an empty list
        if not attendance_counts:
            return []

        # Convert the fetched data into a DataFrame
        df = pd.DataFrame(attendance_counts)

        # Save the DataFrame as an Excel file
        with NamedTemporaryFile(suffix=".xlsx", delete=False) as tmpfile:
            df.to_excel(tmpfile.name, index=False)

        # Close the cursor and database connection
        cursor.close()
        mydb.close()

        # Return the Excel file as a downloadable response
        return FileResponse(tmpfile.name, filename="attendance_count.xlsx")

    except mysql.connector.Error as err:
        # If any error occurs during database operation, raise HTTPException with 500 status code
        raise HTTPException(status_code=500, detail=f"Database error: {err}")
    

@app.get("/employees6/")
def get_employee_list():
    try:
        # Create cursor to execute SQL queries
        cursor = mydb.cursor(dictionary=True)

        # SQL query to get total employees
        total_employees_sql = "SELECT COUNT(*) AS total_employees FROM employee"
        cursor.execute(total_employees_sql)
        total_employees = cursor.fetchone()["total_employees"]

        # SQL query to get employees present today
        present_employees_sql = """
            SELECT COUNT(*) AS present_employees
            FROM attendance
            WHERE Date = CURDATE()
        """
        cursor.execute(present_employees_sql)
        present_employees = cursor.fetchone()["present_employees"]

        # Calculate absent employees as the difference between total and present employees
        absent_employees = total_employees - present_employees

        return {
            "total_employees": total_employees,
            "present_employees": present_employees,
            "absent_employees": absent_employees
        }

    except mysql.connector.Error as err:
        # If any error occurs during database operation, raise HTTPException with 500 status code
        raise HTTPException(status_code=500, detail=f"Database error: {err}")

    finally:
        # Close the cursor and database connection
        if cursor is not None:
            cursor.close()
        mydb.close()


@app.post("/apply_leave/")
def apply_leave(
    employee_name: str = Form(...),
    leave_type: str = Form(...),
    duration: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...), # Default None for single-day leave types
    reason: str = Form(...),
    status: str = "pending"  # Default status is pending
):
    cursor = None
    try:
        # Create cursor to execute SQL queries
        cursor = mydb.cursor()

        # SQL query to insert leave application data into the database
        sql = """
            INSERT INTO leave_applications (employee_name, leave_type, duration, start_date, end_date, reason, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        # Execute the SQL query with the provided leave application data
        cursor.execute(sql, (employee_name, leave_type, duration, start_date, end_date, reason, status))
        mydb.commit()

        return {"message": "Leave application submitted successfully"}

    except mysql.connector.Error as err:
        # If any error occurs during database operation, raise HTTPException with 500 status code
        raise HTTPException(status_code=500, detail=f"Database error: {err}")

    finally:
        # Close the cursor and database connection
        if cursor is not None:
            cursor.close()
        mydb.close()

@app.get("/employee_leaves/")
def get_employee_leaves(date: str):
    cursor = None
    try:
        # Create cursor to execute SQL queries
        cursor = mydb.cursor(dictionary=True)

        # SQL query to retrieve employee leaves for the specified date
        sql = """
            SELECT *
            FROM leave_applications
            WHERE start_date <= %s AND end_date >= %s
        """
        # Execute the SQL query with the provided date
        cursor.execute(sql, (date, date))
        employee_leaves = cursor.fetchall()

        return employee_leaves

    except mysql.connector.Error as err:
        # If any error occurs during database operation, raise HTTPException with 500 status code
        raise HTTPException(status_code=500, detail=f"Database error: {err}")

    finally:
        # Close the cursor and database connection
        if cursor is not None:
            cursor.close()
        mydb.close()

@app.put("/update_leave_status/")
def update_leave_status(leave_id: int, new_status: str):
    cursor = None
    try:
        # Create cursor to execute SQL queries
        cursor = mydb.cursor()

        # SQL query to update the status of the leave application
        sql = """
            UPDATE leave_applications
            SET status = %s
            WHERE id = %s
        """
        # Execute the SQL query to update the status
        cursor.execute(sql, (new_status, leave_id))
        mydb.commit()

        # Check if any rows were affected by the update
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Leave application not found")

        return {"message": "Leave status updated successfully"}

    except mysql.connector.Error as err:
        # If any error occurs during database operation, raise HTTPException with 500 status code
        raise HTTPException(status_code=500, detail=f"Database error: {err}")

    finally:
        # Close the cursor and database connection
        if cursor is not None:
            cursor.close()
        mydb.close()