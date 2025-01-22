# Financial Statement Reading Project v1

Making this public to showcase my full stack engineering abilities. If you download the code and install the right libraries this should work right away--as opposed to my plant stand project where prerequisites include things like soldering circuit boards or building servers...continue reading to see a description of the project and its motivation.

# Background
I've followed stocks and investing since 2010, and have created a database of company data for performing my own personal market research (not included in this repo). 

Who loves manually entering data? I made a program to process excerpts from a corporations 10k and enter them in a database to automate data entry.

# What it does
You give the program either a PDF or an image to process. Usually I get input files from looking up a companies 10k or quarterly on the SEC website, then saving the part of the document which has data tables as a PDF. Pictures from your phone or screenshots from your computer should also work. When you run the code a dialogue box pops up asking you to select a file, and a few seconds later it outputs the data in a database before creating an Excel summary for easy viewing. SQLite is required to run the program, as it stores the full output of the program which can then be standardized and saved in your friendly neighborhood database.

<table>
<tr>
<td align="center">
<strong>Basic Usage</strong><br>
<img src="./assets/basicdemo.gif" height="420">
</td>
</tr>
</table>

# How to set up
- clone the code and create a python virtual environment with the requirements installed
- make sure Tesseract is set up on your operating system if needbe (Windows vs Mac vs Linux can be weird sometimes)
- run the main program (ocr.py is the filename)

## Program logic information
Data is saved to a local database fully managed by the program (SQLite) and doesn't require that you have a separate database or anything. The program is Python, and I wrote it in the times prior to good AI so it's pretty much just high level logic to take low level OCR data and cluster values into rows and columns to discern the data tables from footnotes, text, and other extraneous information. The program is very procedural and only processes images; so the way it works is PDFs are first converted to a series of images, then read into the program using OCR (openCV & Tesseract). The program does 10 or so data transformations as part of the logic, so depite my lack of comments, it isn't actually that hard to debug because you can figure out what function messed up or dropped a number by looking through temp tables created by the program at each step in the code. Most of the issues I've routinely encountered have to do with accurately classifying column names as they take a variety of forms, if anyone wants to be a contributer it would be good to focus on this issue.