import os
import re
import tempfile
import time
import numpy as np
import cv2
from sqlite3.dbapi2 import SQLITE_ALTER_TABLE
from tkinter import Tk
from tkinter import filedialog
from difflib import SequenceMatcher
from pdf2image import convert_from_path
from pytesseract import Output, image_to_data
from tricks import (dict_to_sqlite, list_to_dict, most_frequent, run_SQL,
                    send_to_excel)

def show_boxes(image_data, filename):
	'''function for showing borders around words (visualize the data from image_to_data)
	'''
	image = cv2.imread(filename)
	for i in range(0,len(image_data['line_num'])):
		(x, y, w, h) = (image_data['left'][i], image_data['top'][i], image_data['width'][i], image_data['height'][i])
		cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
	cv2.imshow('Results',image)
	cv2.waitKey(0)
	#boxes = str(os.path.abspath(os.path.dirname( __file__ ))+"\{}.png").format(os.getpid()+1)
	#cv2.imwrite(boxes, image)
	return

#filename = os.path.abspath(os.path.dirname( __file__ ))+'\ca20ad42-8201-4cfe-af72-9965f25f53e9-4.ppm'
#image_data = image_to_data(filename, output_type = Output.DICT)
#show_boxes(image_data, filename)
#import sys
#sys.exit(0)
#---------------------- UNCOMMENT THIS TO SEE BOXES ------------------------------#

def pdf_to_image(filename):
	'''OCR only works on images, so convert all pdfs to a list of images
	'''
	with tempfile.TemporaryDirectory() as path:
		images_from_path = convert_from_path(filename, output_folder=os.path.abspath(os.path.dirname(__file__)))
		print('running for image: ' + str(images_from_path))
		filenames = [i.filename for i in images_from_path]
		return filenames

def group_by_lines(image_lines):
	'''Iterative algorithm: 
		-- if an element is too close to the top of the page to be in its line_num then move down one level
		-- passed==0 if algorithm has converged
	'''
	passed = 0
	for i in range(0,len(image_lines)):
		for j in range(0,len(image_lines[i])):
			first_top = image_lines[i][0]['top']
			if((image_lines[i][j]['top']+5<first_top)):
					if(image_lines[i][j]['line_num']>0):
						image_lines[i][j]['line_num'] -= 1
						passed = 1
					else:
						image_lines[i][j]['text'] = "" #terminate journey of this number, its probably from the top of the sheet
	return image_lines, passed

def left_rule(data):
	'''Iterative algorithm:
		-- makes sure data is clustered and there isn't data outside the columns
		-- practically this would trigger if there's lots of space above or below a word
	'''
	left_thresh = 69
	passed = 0
	for i in range(0,len(data)):
		left = int(data[i]['left'])
		if(i==0):
			if(int(data[i+1]['left'])>(left + left_thresh)):
				print("Removing...(first element)")
				print(data[i])
				print("_________________________________")
				passed = 1
				del data[i]
				return data, passed
			else:
				continue
		elif(i==len(data)-1):
			if(left > int(data[i-1]['left'])+left_thresh):
				print("Removing...(last element)")
				print(data[i])
				print("_________________________________")
				passed = 1
				del data[i]
				return data, passed
			else:
				continue
		elif((left > (int(data[i-1]['left']) + left_thresh) and int(data[i+1]['left'])>(left+left_thresh))):
			print("Removing...(too much space above and below)")
			print(data[i-1]['left'])
			print(data[i])
			print(data[i+1]['left'])
			print("_________________________________")
			passed = 1
			del data[i]
			return data, passed
		else:
			continue

	return data, passed

time_a = time.time()
def implement_left_rule(data):
	for i in range(0,69):	
		data, passed = left_rule(data)
		if(passed==0):
			print("Passed left on run " + str(i) + "? --> " + str(passed))
			print("Time taken: " + str(time.time()-time_a) + " seconds!")
			break
	return data

def isolate_whitespace(data, num_rows, isolated):
	for i in range(0,len(data)):
		count = 0
		surface_1 = [int(data[i]['left']), int(data[i]['left'])+int(data[i]['width'])]
		for j in range(0,len(data)):
			if(data[i]['text']!=data[j]['text']):
				surface_2 = [int(data[j]['left']), int(data[j]['left'])+int(data[j]['width'])]
				if((surface_2[0]>=surface_1[0] and surface_2[0]<=surface_1[1]) or (surface_1[0]>=surface_2[0] and surface_1[0]<=surface_2[1])):
					count+=1
					continue
		if(count<=(num_rows-((3*num_rows)/4))):
			isolated.append(data[i])
			print("________"+str(data[i]['text'])+"____________")
			print(surface_1)
			print(count)
			print(num_rows)
			print(num_rows-((3*num_rows)/4))
			del data[i]
			return data, 1, isolated
	return data, 0, isolated
	
		
def implement_top_rule(data, num_cols, num_rows):
	'''Iterative algorithm:
		-- force table structure on the data, putting numbers into groups of size N
		-- autogenerate the python to implement logic
	'''
	python = """
def top_rule(data):
    top_thresh = 4
    passed = 0
    for i in range(0,len(data),"""+str(num_cols)+"""):
        top = int(data[i]['top'])
        if(i<len(data)-"""+str(num_cols+1)+"""):
"""
	small_if = """if(""" #autogenerate code to remove groups that are too small
	for i in range(1,num_cols):
		small_if +="""(top + top_thresh)>int(data[i+"""+str(i)+"""]['top']) and """
	small_if = " ".join(small_if.split()[0:-1])
	small_if+="): #remove groups smaller than # columns\n"
	small_if+= """                 pass\n"""
	small_if+= """            else:\n"""
	small_if+="""                print("Removing...(group too small")\n"""
	small_if+="""                print(data[i])\n"""
	small_if+="""                print(data[i]['top'])\n"""
	for i in range(1,num_cols):
		small_if+="""                print(data[i+"""+str(i)+"""])\n"""
	small_if+="""                passed = 1\n"""
	small_if+="""                del data[i]\n"""
	small_if+="""                return data, passed\n"""
	python+=("            " + small_if)
	
	large_if = """if("""
	for i in range(1,num_cols):
		large_if +="""top<int(data[i+"""+str(i)+"""]['top']) + top_thresh and """
	large_if += """top + top_thresh<int(data[i+"""+str(num_cols)+"""]['top'])"""
	large_if+="): #remove groups larger than # columns\n"
	large_if+="""                continue\n"""
	large_if+="""            else:"""
	large_if+="""    
                print("Removing... (group too large)")
                remove_list = []
                for j in range(0,len(data)):
                    if((int(data[j]['top'])<=top+top_thresh) and (int(data[j]['top'])>=top-top_thresh)):
                        remove_list.append(data[j])
                        print(data[j])
                data = [k for k in data if str(k['text']+k['top']) not in [str(k['text']+k['top']) for k in remove_list]]
                print("_________________________________")
                passed = 1
                return data, passed\n"""
	python+=("            " + large_if)
	final_if = """elif(i<len(data)-"""+str(num_cols)+"""):\n"""
	temp_if = """if("""
	for i in range(1,num_cols):
		temp_if +="""(top + top_thresh)>int(data[i+"""+str(i)+"""]['top']) and """
	temp_if = " ".join(temp_if.split()[0:-1])
	temp_if+="): #special case for removing groups from the end that are too small\n"
	final_if+=("            " + temp_if)
	final_if+="""                pass\n"""
	final_if+="""            else:"""
	final_if+="""
                print("Removing...(group too small)")
                print(data[i])
                print("_________________________________")
                passed = 1
                del data[i]
                return data, passed
    return data, passed
	"""
	python+=("        " + final_if)
	#print(python)
	exec(python, globals())

	#enforce that data fits the structure of length N rows
	for i in range(0,69):
		print("Length input data: " + str(len(data)))
		data, passed = top_rule(data)
		if(passed==0):
			print("Passed top on run " + str(i) + "? --> " + str(passed))
			print("Time taken: " + str(time.time()-time_a) + " seconds!")
			break

	#isolate data with too much whitespace above and below to be considered part of a column
	isolated = []
	for i in range(0,69):
		print("Length input data: " + str(len(data)))
		data, passed, isolated = isolate_whitespace(data, num_rows, isolated)
		if(passed==0):
			print("Passed isolate_whitespace on run #" + str(i) + "? --> " + str(passed))
			print("Time taken: " + str(time.time()-time_a) + " seconds!")
			break
	
	isolated = sorted(isolated, key = lambda row: int(row['top']), reverse=False)
	print("ISOLATED MY SWIGGA")
	print(isolated)
	print("DATA MY SWIGGA")
	print(data[0:5])

	#enforce that data fits the structure of length N rows
	for i in range(0,69):
		print("Length input data: " + str(len(data)))
		data, passed = top_rule(data)
		if(passed==0):
			print("Passed top on run " + str(i) + "? --> " + str(passed))
			print("Time taken: " + str(time.time()-time_a) + " seconds!")
			break
	return data, isolated

def detect_gaps(data):
	'''figure out how many columns there are and approximate values to use when grouping in the case/when statement
	'''
	lefts = [int(i['left']) for i in data] #ordered list of data from left to right
	gap_thresh = 69 #any space greater than this must be a column break
	results = []
	for i in range(0,len(lefts)):
		if(i<len(lefts)-1):
			if((int(lefts[i+1])-int(lefts[i])) > gap_thresh):
				results.append(int((int(lefts[i+1])-int(lefts[i]))/2 + int(lefts[i])))
	return sorted(results, key = lambda num: num, reverse=False)

def get_column_names(data, num_cols, high_top):
	left_thresh = 150
	for i in data:
		if(int(i['top'])<high_top):
			top = int(i['top'])
			left = int(i['left'])
			row = [i]
			for j in data:
				if(int(j['top'])<high_top):
					if(i['text']!=j['text']):
						if(top==int(j['top']) and (left+left_thresh)<int(j['left'])):
							row.append(j)
							left = int(j['left'])
			if len(row)==num_cols:
				columns = [k['text'].strip() for k in row]
				return columns
	return []

def group_by_columns(image_lines, num_cols, num_rows):
	'''get table from right side of the page
	'''

	# get right 3/4 of data from page
	SQL = """drop table if exists right_side;"""
	run_SQL(SQL, commit_indic='y')
	SQL = """
		create table right_side as
		select cast(left as 'decimal') as left, text, cast(top as 'decimal') as top, cast(width as 'decimal') as width
		from image_table
		where text not in ('$',' ', 'S$','§')
		and cast(left as 'decimal')>(select max(cast(left as 'decimal'))/4 from image_table)
		order by cast(top as 'decimal') asc, cast(left as 'decimal') asc;"""
	run_SQL(SQL, commit_indic='y')

	# look at data left to right and remove stuff that doesn't appear to line up with a column
	time_a = time.time()
	SQL = """select distinct text, left, top, width from right_side order by cast(left as 'decimal') asc;"""
	data = run_SQL(SQL)
	data = implement_left_rule(data)
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"right_side_1")
	print("Time taken implement_left_rule: " + str(time.time()-time_a) + " seconds!")

	# look at data top to bottom and group into rows of data
	time_a  = time.time()
	SQL = """select distinct text, left, top, width from right_side_1 order by cast(top as 'decimal') asc;"""
	data = run_SQL(SQL)
	data, isolated = implement_top_rule(data, num_cols, num_rows)
	print(data)
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"right_side_2")
	print("Time taken implement_top_rule: " + str(time.time()-time_a) + " seconds!")

	# define column boundaries for writing SQL case to label column number
	time_a = time.time()
	SQL = """select distinct text, left, top from right_side_2 order by cast(left as 'decimal') asc;"""
	data = run_SQL(SQL)
	results = [0] + detect_gaps(data)
	print("Column boundaries: ")
	print(results)
	SQL = """drop table if exists right_side_3;"""
	run_SQL(SQL, commit_indic='y')
	SQL = """
		create table right_side_3 as
		select distinct text, left, top, case
		"""
	counter = 1
	for i in range(0,len(results)-1):
		SQL += " when cast(left as 'decimal') between " + str(results[i]) + " and " + str(results[i+1]) + " then 'group_"+str(counter) + "'"
		counter+=1
	SQL += " when cast(left as 'decimal')>=" + str(results[-1]) + " then 'group_"+str(counter) + "'"
	SQL += """ end as col_num
		from right_side_2;
		"""
	print(SQL)
	run_SQL(SQL, commit_indic='y')

	# make sure that top value is normalized for stuff on the same line
	data = run_SQL("select * from right_side_3 order by cast(top as 'decimal') asc;")
	print(num_cols)
	for i in range(0,len(data),num_cols):
		top = str(data[i]['top'])
		for j in range(0,num_cols):
			data[i+j]['top'] = top
	SQL = """drop table if exists right_side_4;"""
	run_SQL(SQL, commit_indic='y')
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"right_side_4")

	# extract names of columns from page data, only consider those in top quarter of data (header must be near or at the top)
	data = run_SQL("select * from right_side_4 order by cast(top as 'decimal') asc, cast(left as 'decimal');")
	high_top = [i['top'] for i in sorted(data, key=lambda row: int(row['top']))]
	high_top = high_top[int(len(high_top)/4)]
	print(high_top)
	columns = get_column_names(isolated, num_cols, int(high_top))
	if(len(columns)==0):
		columns = [i['text'] for i in data[0:num_cols]]
		data = data[num_cols:]
	print(columns)
	for i in range(0,len(data),num_cols):
		for j in range(0,num_cols):
			data[i+j]['column'] = columns[j]

	#join in data from step 1 (variable, line_num, rank)
	for i in range(0,len(data)):
		for j in range(0,len(image_lines)):
			if(int(data[i]['top'])<=int(image_lines[j]['top'])+4 and int(data[i]['top'])>=int(image_lines[j]['top'])-4):
				data[i]['variable'] = image_lines[j]['variable']
				data[i]['line_num'] = str(j)
				data[i]['page_num'] = image_lines[j]['page_num']

	data = [i for i in data if 'variable' in i.keys()]
	for i in range(0,len(data)):
		data[i]['text'] = data[i]['text'].replace(",","").replace("..",".").replace(".,",".").replace(",.",".")
	data = replace_dashes_new(data)
	SQL = """drop table if exists right_side_5;"""
	run_SQL(SQL, commit_indic='y')
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"right_side_5")


	SQL = """drop table if exists right_side_6;"""
	run_SQL(SQL, commit_indic='y')
	SQL = """
		create table right_side_6 as
		select distinct variable, cast(replace(text,'—','-') as 'decimal') as value, column, cast(line_num as 'decimal') as line_num,
		cast(left as 'decimal') as left, cast(top as 'decimal') as top, cast(page_num as 'decimal') as page_num, col_num
		from right_side_5;
		"""
	run_SQL(SQL, commit_indic='y')

def fix_image_lines(image_lines):
	'''part 2 of algorithm, fix data structure to force Python line index to equal line_num
	   		-- force digits to be after words (TODO: flawed logic, should be ordered left to right)
	'''
	max_line_num = max([i['line_num'] for i in image_lines[-1]])
	temp_list = [[] for i in range(0,max_line_num+1)]
	for i in range(0,len(image_lines)):
		for j in range(0,len(image_lines[i])):
			temp_list[image_lines[i][j]['line_num']].append(image_lines[i][j])
	return_list = []
	for i in range(0,len(temp_list)):
		first_half = [] #anchor the first word to ensure lines are constant
		second_half = []
		for j in [k for k in temp_list[i] if len(k)>0]:
			if(j['text'].replace(",","").replace("$","").replace("(","").replace(")","").replace(" ","").replace("-","").replace("0.","").strip().lower().isdigit()):
				second_half.append(j)
			else:
				first_half.append(j)
		return_list.append(first_half+second_half)
	return return_list

def save_image_data(image_data):
	'''save cleaned data from OCR program
	'''
	pattern = re.compile(r'[A-Z][0-9]')
	columns = ['left','top','width','height','text']
	data_dict = {i:[] for i in columns}
	for i in range(0,len(image_data['text'])):
		if(image_data['text'][i] not in ('',' ',None,'$','§')):
			if(len(pattern.findall(image_data['text'][i]))>0):
				print("TRIGGERED!!")
				print(image_data['text'][i])
			image_data['text'][i] = image_data['text'][i].replace("A4","4").replace("G4","34").replace("G6","36")
			if(len(image_data['text'][i].strip())>1):
				if("." in image_data['text'][i] and image_data['text'][i].replace("(","").replace(")","").replace("0.","").replace(".","").replace(",","").strip().isdigit()):
					if(image_data['text'][i].strip()[0]!="0"):
						image_data['text'][i] = image_data['text'][i].replace(".",",")
			if(image_data['text'][i][0]=="0"):
				image_data['text'][i] = "0." + image_data['text'][i][1:]
			for key in columns:
				data_dict[key].append(str(image_data[key][i]))
	print('Number of rows going in... '+ str(len(data_dict['text']))) #how long is the dict we're getting out?
	dict_to_sqlite(data_dict,'image_table')
	return

def remove_lines(filename):
	'''get rid of horizontal lines in the financial statement (interfears with OCR)
	'''
	img = cv2.imread(filename)
	img = cv2.resize(img, None, fx=1.2, fy=1.2, interpolation=cv2.INTER_CUBIC)
	img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
	kernel = np.ones((1, 1), np.uint8)
	img = cv2.dilate(img, kernel, iterations=1)
	img = cv2.erode(img, kernel, iterations=1)
	lns = cv2.ximgproc.createFastLineDetector(length_threshold=20).detect(img)
	#img = cv2.threshold(cv2.medianBlur(img, 3), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
	if lns is not None:
		for ln in lns:
			(x_start, y_start, x_end, y_end) = [int(i) for i in ln[0]]
			if(abs(abs(float(y_start))-abs(float(y_end)))<5):
				#print("x_start: " + str(x_start) + "  " + "x_end: " + str(x_end) + "  y_start: " + str(y_start) + "  " + "y_end: " + str(y_end))
				cv2.line(img, (x_start-(x_end-x_start), y_start+2), (x_end, y_end+2), (255, 255, 255), thickness=4)
	#thr = adaptiveThreshold(gry, 255, ADAPTIVE_THRESH_MEAN_C, THRESH_BINARY, 21, 1)
	filename = str(os.path.abspath(os.path.dirname( __file__ ))+"\{}.png").format(os.getpid())
	cv2.imwrite(filename, img)
	time_a = time.time()
	image_data = image_to_data(filename, output_type = Output.DICT)
	print("Time taken image_to_data: " + str(time.time()-time_a) + " seconds!")
	return image_data, filename

def replace_dashes(image_lines):
	'''turn dashes into zeros, reposition dashes so that the "top" value isn't so different from other numbers
	'''
	for i in range(0,len(image_lines)):
		for j in range(0,len(image_lines[i])):
			if(image_lines[i][j]['text'].strip()==b'\xe2\x80\x94'.decode('utf-8')):
				image_lines[i][j]['text'] = str(0)
				image_lines[i][j]['top'] = float(image_lines[i][j]['top']) - 10
			elif(image_lines[i][j]['text'].strip()[0]=="(" and image_lines[i][j]['text'].strip()[-1]==")"):
				if(image_lines[i][j]['text'].replace("(","").replace(")","").replace("0.","").replace(".","").replace(",","").strip().isdigit()):
					image_lines[i][j]['text'] = str("—" + image_lines[i][j]['text'][1:-1])
				else:
					print(image_lines[i][j]['text'])
	return image_lines

def replace_dashes_new(data):
	'''turn dashes into zeros, reposition dashes so that the "top" value isn't so different from other numbers
	'''
	for i in range(0,len(data)):
		if(data[i]['text'].strip()==b'\xe2\x80\x94'.decode('utf-8')):
			data[i]['text'] = str(0)
			data[i]['top'] = float(data[i]['top']) - 10
		elif(data[i]['text'].strip()[0]=="(" and data[i]['text'].strip()[-1]==")"):
			if(data[i]['text'].replace("(","").replace(")","").replace("0.","").replace(".","").replace(",","").strip().isdigit()):
				data[i]['text'] = str("—" + data[i]['text'][1:-1])
			else:
				print(data[i]['text'])
	return data

def detect_dates(data, num_cols):
	calendar_months = ['january','february','march','april','may','june','july','august','september','october','november','december']
	data = sorted(data, key=lambda row: int(row['top']))
	top_thresh=4
	for i in range(1,len(data)):
		if(int(data[i]['top'])<int(data[i-1]['top'])+top_thresh):
			data[i]['top'] = data[i-1]['top']
	data = sorted(data, key=lambda row: (int(row['top']), int(row['left'])))
	new_data = []
	top = data[0]['top']
	temp_list = []
	for i in data:
		if(int(i['top'])!=top):
			new_data.append(temp_list)
			top = int(i['top'])
			temp_list = [i]
		else:
			temp_list.append(i)
	for i in range(0,len(new_data)):
		possible_dates = []
		for j in range(0,len(new_data[i])):
			passed = 0
			for month in calendar_months:
				if(SequenceMatcher(None, new_data[i][j]['text'].lower(), month).ratio()>=.80):
					print("HERE SWIGGA 1")
					new_data[i][j]['text'] = month
					passed = 1
					break
			if(passed==1):
				try:
					if(new_data[i][j+1]['text'].strip().replace(",","").isdigit() and new_data[i][j+2]['text'].strip().replace(",","").isdigit()):
						possible_dates.append([new_data[i][j], new_data[i][j+1], new_data[i][j+2]])
					else:
						print("HERE SWIGGA 2")
						raise Exception("Skip to next try...")
				except:
					try:
						if(new_data[i][j+1]['text'].strip().replace(",","").isdigit()):
							print("HERE SWIGGA 3")
							possible_dates.append([new_data[i][j], new_data[i][j+1]])
							print("HERE SWIGGA 4")
						else:
							possible_dates.append([new_data[i][j]])
					except:
						possible_dates.append([new_data[i][j]])
		if(len(possible_dates)==num_cols):
			return possible_dates
	return None
		
def scrape_financials(full_image_data):
	'''scrapes financial data from chosen set of images
	'''
	SQL = """delete from financials;""" #clear out temp table
	run_SQL(SQL, commit_indic='y')

	#apply table processing logic to each image
	for page_num in range(0,len(full_image_data)):
		image_data = full_image_data[page_num]
		time_a = time.time()
		save_image_data(image_data) #put image data into SQL
		print("Time taken save_image_data: " + str(time.time()-time_a) + " seconds!")
		time_a = time.time()
		temp_data = {'text': [], 'top': [], 'left': [], 'line_num': []}
		for i in range(0,len(image_data['text'])):
			if(image_data['text'][i]!=""):
				temp_data['text'].append(image_data['text'][i])
				temp_data['top'].append(image_data['top'][i])
				temp_data['left'].append(image_data['left'][i])
				temp_data['line_num'].append(image_data['line_num'][i])
		image_data = temp_data #initialize data for single page
		image_lines = [[{key: image_data[key][0] for key in ('text','top','left')}]] #initialize list of lists data structure, line_num scheme
		image_lines[0][0]['line_num'] = 0
		tack_on = []
		line_num = 1
		
		#only consider words within 100 of left side of page as a line marker
		for i in range(0,len(image_data['text'])):
			if image_data['left'][i]<115:
				if(image_data['top'][i]>image_lines[len(image_lines)-1][0]['top']+5):
					line = {key: image_data[key][i] for key in ('text','top','left','line_num')}
					line['line_num'] = line_num
					line_num+=1
					image_lines.append([line])
				else:
					tack_on.append({key: image_data[key][i] for key in ('text','top','left','line_num')})
			else:
				tack_on.append({key: image_data[key][i] for key in ('text','top','left','line_num')})

		#last item in list includes all other data, sorted from top to bottom
		tack_on = sorted(tack_on, key = lambda num: num['top'], reverse=True)
		for i in tack_on:
			image_lines[-1].append(i)
		max_line_num = len(image_lines)-1
		for i in range(0,len(image_lines[-1])):
			image_lines[-1][i]['line_num'] = max_line_num
		for i in range(0,len(image_lines)):
			image_lines[i] = [k for k in image_lines[i] if k['text'].strip()!=""]

		image_lines = replace_dashes(image_lines)

		print(str(max_line_num) + " lines initialized!!! :D !!!")

		time_a = time.time()
		for i in range(0,100):	
			image_lines, passed = group_by_lines(image_lines)
			image_lines = fix_image_lines(image_lines)
			if(passed==0):
				print("___ Passed image lines sort on run ___: " + str(i) + " --> ")
				break
		
		for i in range(0,3):
			print("_____________________________")
			print(image_lines[i])

		# sort lines left to right
		time_a = time.time()
		for i in range(0,len(image_lines)):
			image_lines[i] = sorted(image_lines[i], key = lambda var: var['left'], reverse = False)

		for i in range(0,len(image_lines)):
			for j in range(1,len(image_lines[i])):
				if(image_lines[i][j]['text']==image_lines[i][j-1]['text'] and image_lines[i][j]['top']==image_lines[i][j-1]['top']):
					image_lines[i][j]['text'] = ""

		top_data = image_lines[0]+image_lines[1]

		for i in range(0,len(image_lines)):
			image_lines[i] = {'text': [k['text'].replace("$","").replace(",","").strip().lower() for k in image_lines[i] if len(k['text'].replace("$","").strip().lower())>0],
							 'top': image_lines[i][0]['top'], 'page_num': str(page_num+1)}

		for i in range(0,len(image_lines)):
			values = []
			variable = ""
			for j in image_lines[i]['text']:
				if(j.replace(b'\xe2\x80\x94'.decode('utf-8'),"").replace("0.","").replace(".","").replace("-","").strip().isdigit()):
					values.append(j)
				else:
					variable += " " + str(j)
			image_lines[i]['variable'] = variable.replace("\"","").replace("§","")
			image_lines[i]['values'] = values
			
		num_cols = most_frequent([len(i['values']) for i in image_lines])
		num_rows = len(image_lines)
		print("num_cols:" + str(num_cols))
		print("num_rows:" + str(num_rows))

		potential_dates = detect_dates(top_data, num_cols)
		print(potential_dates)
		import sys
		sys.exit(0)

		group_by_columns(image_lines, num_cols, num_rows)
		print("Inputting scraped financial data...")
		SQL = """
		insert into financials
		select * from right_side_6;
		"""
		run_SQL(SQL, commit_indic='y', database=str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))

Tk().withdraw()
filename = filedialog.askopenfilename()
#filename = os.path.abspath(os.path.dirname( __file__ ))+'\ca20ad42-8201-4cfe-af72-9965f25f53e9-1.ppm' #manual for testing
#filename = os.path.abspath(os.path.dirname( __file__ ))+'\\ca20ad42-8201-4cfe-af72-9965f25f53e9-2.ppm' #manual for testing
#filename = os.path.abspath(os.path.dirname( __file__ ))+'\\ca20ad42-8201-4cfe-af72-9965f25f53e9-3.ppm' #manual for testing
#filename = os.path.abspath(os.path.dirname( __file__ ))+'\\7c30942b-b2a5-4713-9354-afd1f957545e-1.ppm' #manual for testing

#if it's a PDF, convert to image first
start_time = time.time()
try:
	images = pdf_to_image(filename)
	print("PDF")
	print(images)
except:
	print("image")
	images = [filename]

full_image_data = []
for old_image in images:
	time_a = time.time()
	image_data, image = remove_lines(old_image)
	#show_boxes(image_data, image)
	#import sys
	#sys.exit(0)
	print(" ### Time taken to scrape data from image: " + str(time.time()-time_a) + " seconds!")
	full_image_data.append(image_data)
	os.remove(image)
	if(len(images))>1:
		os.remove(old_image)  

scrape_financials(full_image_data)

def output_to_excel():
	'''transform most recently scraped data into traditional spread format
	'''
	SQL = """
		select * from (
		select distinct page_num, line_num, variable, sum(case
		when column=2020 then value end) as this_year, sum(case 
		when column=2019 then value end) as last_year, sum(case
		when column=2018 then value end) as year_before, count(*) as total
		from right_side_6
		group by page_num, line_num, variable
		order by page_num, line_num)
		where total<=3;
		"""
	data = run_SQL(SQL, database=str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))
	data = [{'variable': i['variable'], '2020': i['this_year'], '2019': i['last_year'], '2018': i['year_before']} for i in data]
	data = list_to_dict(data)

	send_to_excel(os.path.dirname(__file__),data,"Financial Statement Output",clear_indic='n')

output_to_excel()

print("finished running in: " + str(time.time()-start_time) + " seconds")

