import os
import tempfile
import time
from tkinter import Tk
from tkinter.filedialog import askopenfilename

import pandas as pd
from cv2 import (ADAPTIVE_THRESH_MEAN_C, COLOR_BGR2GRAY, THRESH_BINARY,
                 adaptiveThreshold, cvtColor, imread, imshow, imwrite, line,
                 rectangle, waitKey, ximgproc)
from pdf2image import convert_from_path
from pytesseract import Output
from pytesseract import image_to_data as Tessa_image_to_data
from pytesseract import image_to_string as Tessa_image_to_string

from tricks import (dict_to_sqlite, list_to_dict, most_frequent, run_SQL,
                    send_to_excel)

pd.options.mode.chained_assignment = None  # default='warn'

def show_rectangles(image_data, filename):
	'''function for showing borders around words (visualize the data from image_to_data)
	'''
	image = imread(filename)
	for i in range(0,len(image_data['line_num'])):
		(x, y, w, h) = (image_data['left'][i], image_data['top'][i], image_data['width'][i], image_data['height'][i])
		rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
	imshow('Results',image)
	waitKey(0)
	return

#get image from PDF
def pdf_to_image(filename):
	with tempfile.TemporaryDirectory() as path:
		images_from_path = convert_from_path(filename, output_folder=os.path.abspath(os.path.dirname(__file__)))
		print('running for image: ' + str(images_from_path))
		filenames = [i.filename for i in images_from_path]
		return filenames

def group_by_lines(image_lines):
	'''
	 --  do the iterative migration top to bottom, if an element is too close to the top of the page to be in its index then move down by one
	 -- "passed" indicates weather or not the algorithm has yet converged
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
	'''
	-- get rid of extra stuff that may be above/below table or in the middle of the page
	-- another way of detecting if there's too much empty space above or below a word
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
			print(data[i])
			print("_________________________________")
			passed = 1
			del data[i]
			return data, passed
		else:
			continue

	return data, passed

def top_rule(data):
	'''
	-- force table like structure onto data on right side of page
	-- things need to be in groups of twos, threes, etc...
	'''
	top_thresh = 4
	passed = 0
	for i in range(0,len(data),3):
		top = int(data[i]['top'])
		if(i<len(data)-4):
			if((top + top_thresh)>int(data[i+1]['top']) and (top + top_thresh)>int(data[i+2]['top'])):
				pass
			else:
				print("Removing...(group too small)")
				print(data[i])
				print(str(data[i]['top']))
				print(str(data[i+1]['top']))
				print(str(data[i+2]['top']))
				print("_________________________________")
				passed = 1
				del data[i]
				return data, passed
			if(top<int(data[i+1]['top']) + top_thresh and top<int(data[i+2]['top']) + top_thresh and top+top_thresh<int(data[i+3]['top'])):
				continue
			else:
				print("Removing... (group too large)")
				remove_list = []
				for j in range(0,len(data)):
					if((int(data[j]['top'])<=top+top_thresh) and (int(data[j]['top'])>=top-top_thresh)):
						remove_list.append(data[j])
						print(data[j])
				data = [k for k in data if k['text'] not in [k['text'] for k in remove_list]]
				print("_________________________________")
				passed = 1
				return data, passed
		elif(i<len(data)-3):
			if((top + top_thresh)>int(data[i+1]['top']) and (top + top_thresh)>int(data[i+2]['top'])):
				pass
			else:
				print("Removing...(group too small)")
				print(data[i])
				print("_________________________________")
				passed = 1
				del data[i]
				return data, passed

	return data, passed

def detect_gaps(data):
	lefts = [int(i['left']) for i in data]
	gap_thresh = 69
	results = []
	for i in range(0,len(lefts)):
		if(i<len(lefts)-1):
			if((int(lefts[i+1])-int(lefts[i])) > gap_thresh):
				results.append(int((int(lefts[i+1])-int(lefts[i]))/2 + int(lefts[i])))
	return sorted(results, key = lambda num: num, reverse=False)

def group_by_columns():
	SQL = """drop table if exists right_side;"""
	run_SQL(SQL, commit_indic='y')
	#all the data on this page
	SQL = """
		create table right_side as
		select cast(left as 'decimal') as left, text, cast(top as 'decimal') as top
		from image_table
		where text not in ('$',' ')
		and cast(left as 'decimal')>(select max(cast(left as 'decimal'))/2 from image_table)
		order by cast(top as 'decimal') asc, cast(left as 'decimal') asc;"""
	run_SQL(SQL, commit_indic='y')
	
	#process data top to bottom
	SQL = """select distinct text, left, top from right_side order by cast(top as 'decimal') asc;"""
	data = run_SQL(SQL)
	for i in range(0,69):
		print("Length input data: " + str(len(data)))
		data, passed = top_rule(data)
		if(passed==0):
			print("Passed top on run " + str(i) + "? --> " + str(passed))
			break
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"right_side_1")

	#process data left to right
	SQL = """select distinct text, left, top from right_side_1 order by cast(left as 'decimal') asc;"""
	data = run_SQL(SQL)
	for i in range(0,69):	
		data, passed = left_rule(data)
		if(passed==0):
			print("Passed left on run " + str(i) + "? --> " + str(passed))
			break

	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"right_side_2")

	SQL = """select distinct text, left, top from right_side_2 order by cast(left as 'decimal') asc;"""
	data = run_SQL(SQL)
	results = detect_gaps(data)
	print(results)

	#SQL = """drop table if exists right_side_3;"""
	#run_SQL(SQL, commit_indic='y')
	#SQL = ""
	#for i in results:

	#run_SQL(SQL, commit_indic='y')

def fix_image_lines(image_lines):
	'''part 2 of algorithm, fix reweighted list items so they're grouped right
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
	columns = ['left','top','width','height','text']
	data_dict = {i:[] for i in columns}
	for i in range(0,len(image_data['text'])):
		if(image_data['text'][i] not in ('',' ',None,'$','§')):
			image_data['text'][i] = image_data['text'][i].replace("A4","4")
			if(image_data['text'][i][0]=="0"):
				image_data['text'][i] = "0." + image_data['text'][i][1:]
			for key in columns:
				data_dict[key].append(str(image_data[key][i]))
	print('Number of rows going in... '+ str(len(data_dict['text']))) #how long is the dict we're getting out?
	dict_to_sqlite(data_dict,'image_table')
	return

def remove_lines(filename):
	""" get rid of horizontal lines in the financial statement (interfears with optical character recognition)
	"""
	img = imread(filename)
	gry = cvtColor(img, COLOR_BGR2GRAY)
	lns = ximgproc.createFastLineDetector(length_threshold=20).detect(gry)
	if lns is not None:
		for ln in lns:
			(x_start, y_start, x_end, y_end) = [int(i) for i in ln[0]]
			if(abs(abs(float(y_start))-abs(float(y_end)))<5):
				#print("x_start: " + str(x_start) + "  " + "x_end: " + str(x_end) + "  y_start: " + str(y_start) + "  " + "y_end: " + str(y_end))
				line(gry, (x_start-(x_end-x_start), y_start), (x_end, y_end), (255, 255, 255), thickness=4)
	thr = adaptiveThreshold(gry, 255, ADAPTIVE_THRESH_MEAN_C, THRESH_BINARY, 21, 23)
	filename = str(os.path.abspath(os.path.dirname(__file__))+"{}.png").format(os.getpid())
	imwrite(filename, gry)
	image_data = Tessa_image_to_data(thr, output_type = Output.DICT)
	return image_data, filename

#gui
Tk().withdraw()
#filename = askopenfilename()
#filename = os.path.abspath(os.path.dirname( __file__ ))+'\\9f9416d6-7507-4822-a10e-07cfdbce3157-2.ppm' #manual for testing
filename = os.path.abspath(os.path.dirname( __file__ ))+'\ca20ad42-8201-4cfe-af72-9965f25f53e9-4.ppm' #manual for testing

#if it's a PDF, convert to image first
start_time = time.time()
try:
	images = pdf_to_image(filename)
	print("PDF")
except:
	images = [filename]
	print("image")

full_image_data = []
for image in images:
	image_data, filename = remove_lines(filename)
	save_image_data(image_data) #put image data into SQL
	full_image_data.append(image_data)
	os.remove(filename)

group_by_columns()
import sys
sys.exit(0)

SQL = """delete from financials;"""
run_SQL(SQL, commit_indic='y', database=str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))
for image_data in full_image_data:
	temp_data = {'text': [], 'top': [], 'left': [], 'line_num': []}
	for i in range(0,len(image_data['text'])):
		if(image_data['text'][i]!=""):
			temp_data['text'].append(image_data['text'][i])
			temp_data['top'].append(image_data['top'][i])
			temp_data['left'].append(image_data['left'][i])
			temp_data['line_num'].append(image_data['line_num'][i])
	image_data = temp_data
	image_lines = [[{key: image_data[key][0] for key in ('text','top','left')}]]
	image_lines[0][0]['line_num'] = 0
	tack_on = []
	line_num = 1 
	for i in range(0,len(image_data['text'])):
		if image_data['left'][i]<100:
			if(image_data['top'][i]>image_lines[len(image_lines)-1][0]['top']+5):
				line = {key: image_data[key][i] for key in ('text','top','left','line_num')}
				line['line_num'] = line_num
				line_num+=1
				image_lines.append([line])
			else:
				tack_on.append({key: image_data[key][i] for key in ('text','top','left','line_num')})
		else:
			tack_on.append({key: image_data[key][i] for key in ('text','top','left','line_num')})

	tack_on = sorted(tack_on, key = lambda num: num['top'], reverse=True)
	for i in tack_on:
		image_lines[-1].append(i)
	max_line_num = len(image_lines)-1
	
	for i in range(0,len(image_lines[-1])):
		image_lines[-1][i]['line_num'] = max_line_num

	for i in range(0,len(image_lines)):
		image_lines[i] = [k for k in image_lines[i] if k['text'].strip()!=""]

	for i in range(0,len(image_lines)):
		for j in range(0,len(image_lines[i])):
			if(image_lines[i][j]['text'].strip()==b'\xe2\x80\x94'.decode('utf-8')):
				image_lines[i][j]['text'] = str(0)
				image_lines[i][j]['top'] = float(image_lines[i][j]['top']) - 10
			elif(image_lines[i][j]['text'].strip()[0]=="(" and image_lines[i][j]['text'][-1].strip()==")"):
				if(image_lines[i][j]['text'].replace("(","").replace(")","").replace("0.","").replace(".","").strip().isdigit()):
					image_lines[i][j]['text'] = str("—" + image_lines[i][j]['text'][1:-1])

	original_image_lines = [i for i in image_lines]

	#for i in image_lines:
	#	print(i[0]['text'])
	#	print(i[0]['line_num'])
	#for i in image_lines:
	#	print(min([j['line_num'] for j in i]))
	#for i in image_lines:
	#	print(len(i))
	#for i in image_lines:
	#	if(len(i)>0):
	#		print(i[0]['text'])

	for i in range(0,100):	
		image_lines, passed = group_by_lines(image_lines)
		image_lines = fix_image_lines(image_lines)

	# sort lines left to right
	for i in range(0,len(image_lines)):
		image_lines[i] = sorted(image_lines[i], key = lambda var: var['left'], reverse = False)

	for i in range(0,len(image_lines)):
		for j in range(1,len(image_lines[i])):
			if(image_lines[i][j]['text']==image_lines[i][j-1]['text'] and image_lines[i][j]['top']==image_lines[i][j-1]['top']):
				image_lines[i][j]['text'] = ""

	print("Passed? " + str(passed))
	print("___________________________________")
	print([i for i in image_lines[0]])
	print("___________________________________")
	print([i['text'] for i in image_lines[1]])
	print("___________________________________")
	print([i['text'] for i in image_lines[7]])

	for i in range(0,len(image_lines)):
		image_lines[i] = {'text': [k['text'].replace("$","").replace(",","").strip().lower() for k in image_lines[i] if len(k['text'].replace("$","").strip().lower())>0]}
	company_name = "UNKNOWN"
	for i in image_lines:
		for j in range(0,len(i['text'])):
			if 'inc.' in i['text'][j] or 'llc.' in i['text'][j]:
				try:
					company_name = i['text'][j-1]
				except:
					company_name = 'INC AT START OF LINE'
	
	for i in range(0,len(image_lines)):
		values = []
		variable = ""
		for j in image_lines[i]['text']:
			if(j.replace(b'\xe2\x80\x94'.decode('utf-8'),"").replace("0.","").replace(".","").replace("-","").strip().isdigit()):
				values.append(j)
			else:
				variable += " " + str(j)
		image_lines[i]['variable'] = variable.replace("\"","")
		image_lines[i]['values'] = values
		
	data_dict = {'rank': [],'variable': [], 'year': [], 'value': []}
	num_years = most_frequent([len(i['values']) for i in image_lines])

	for i in range(0,len(image_lines)):
		if(len(image_lines[i]['values'])==num_years and image_lines[i]['variable']!=""):
			for j in range(0,num_years):
				data_dict['rank'].append(str(i))
				data_dict['variable'].append(image_lines[i]['variable'].strip().lower())
				data_dict['year'].append(str(2020-j))
				data_dict['value'].append(image_lines[i]['values'][j])
		elif(len(image_lines[i]['values'])==0 and image_lines[i]['variable']!=""):
			data_dict['rank'].append(str(i))
			data_dict['variable'].append(image_lines[i]['variable'].strip().lower())
			data_dict['year'].append("HEADING")
			data_dict['value'].append("HEADING")

	print("_____Inputting first half______")
	[print(len(data_dict[i])) for i in data_dict.keys()]
	dict_to_sqlite(data_dict, "financials_temp_1")
	SQL = """
	insert into financials
	select * from financials_temp_1;
	"""
	run_SQL(SQL, commit_indic='y', database=str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))

SQL = """
	select * from (
	select distinct rank, variable, sum(case
	when year=2020 then value end) as this_year, sum(case 
	when year=2019 then value end) as last_year, sum(case
	when year=2019 then value end) as year_before, count(*) as total
	from financials
	group by rank, variable
	order by cast(rank as 'decimal'))
	where total<=3;
	"""
data = run_SQL(SQL, database=str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))
data = [{'variable': i['variable'], '2020': i['this_year'], '2019': i['last_year'], '2018': i['year_before']} for i in data]
data = list_to_dict(data)

send_to_excel(os.path.dirname(__file__),data,"Financial Statement Output",clear_indic='n')

print("finished running in: " + str(time.time()-start_time) + " seconds")

