import os
import re
import cv2
import time
import tempfile
import numpy as np
from tkinter import Tk, filedialog
from difflib import SequenceMatcher
from pdf2image import convert_from_path
from pytesseract import Output, image_to_data
from tricks import (dict_to_sqlite, update_in_table, list_to_dict, most_frequent, run_SQL, send_to_excel)

def show_boxes(image_data, filename):
	'''function for showing borders around words (visualize the data from image_to_data)
	'''
	image = cv2.imread(filename)
	for i in range(0,len(image_data['line_num'])):
		(x, y, w, h) = (image_data['left'][i], image_data['top'][i], image_data['width'][i], image_data['height'][i])
		cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
	boxes = str(os.path.abspath(os.path.dirname( __file__ ))+"\{}.png").format(os.getpid()+1)
	cv2.imwrite(boxes, image)
	return

def pdf_to_image(filename):
	'''OCR only works on images, so convert all pdfs to a list of images
	'''
	with tempfile.TemporaryDirectory() as path:
		images_from_path = convert_from_path(filename, output_folder=str(os.path.abspath(os.path.dirname(__file__))+"\\temp"))
		print('running for image: ' + str(images_from_path))
		filenames = [i.filename for i in images_from_path]
		return filenames

def output_results():
	'''transform most recently scraped data into traditional spread format
	'''
	SQL = "select distinct col_num, column from financials;"
	data = run_SQL(SQL)
	col_nums = sorted(list(set([i['col_num'] for i in data])))
	case_sql = ""
	for col_num in col_nums:
		column = str([i['column'] for i in data if i['col_num']==col_num][0])
		case_sql += """, sum(case when col_num="""+str(col_num)+""" then value end) as '"""+column+"""' \n"""
	SQL = """
		select * from (
		select distinct page_num, line_num, variable
		"""	+ case_sql + """
		from financials
		group by page_num, line_num, variable
		order by cast(page_num as 'decimal'), cast(line_num as 'decimal'));
		"""
	data = list_to_dict(run_SQL(SQL))
	send_to_excel(os.path.dirname(__file__),data,"Financial Statement Output",clear_indic='y',headings='y')

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
	return image_lines, passed

def left_rule(data):
	'''Iterative algorithm:
		-- makes sure data is clustered and there isn't data outside the columns
		-- practically this would trigger if there's lots of space above or below a word
	'''
	left_thresh = 69
	passed = 0
	for i in range(0,len(data)):
		text = data[i]['text']
		try:
			text = int(text)
			if(text>=1969 and text<=2023):
				continue
		except:
			pass
		left = int(data[i]['left'])
		if(i==0):
			if(int(data[i+1]['left'])>(left + left_thresh)):
				passed = 1
				del data[i]
				return data, passed
			else:
				continue
		elif(i==len(data)-1):
			if(left > int(data[i-1]['left'])+left_thresh):
				passed = 1
				del data[i]
				return data, passed
			else:
				continue
		elif((left > (int(data[i-1]['left']) + left_thresh) and int(data[i+1]['left'])>(left+left_thresh))):
			passed = 1
			del data[i]
			return data, passed
		else:
			continue
	return data, passed

def implement_left_rule(data):
	for i in range(0,69):
		data, passed = left_rule(data)
		if(passed==0):
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
			del data[i]
			return data, 1, isolated
	return data, 0, isolated

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
	left_thresh = 100
	front,back = [],[]
	for i in data:
		try:
			if(int(i['text'].strip())>1969 and int(i['text'].strip())<2023):
				front.append(i)
		except:
			back.append(i)
	print("high top")
	data = front+back
	for i in data:
		if(int(i['top'])<high_top):
			top = int(i['top'])
			left = int(i['left'])
			row = [i]
			count = len([k for k in data if int(k['top'])>=top-5 and int(k['top'])<=top+5])
			if(count<(num_cols+2)):
				for j in data: 
					if(int(j['top'])<high_top):
						if((int(i['top'])+int(i['left'])+int(i['width']))!=(int(j['top'])+int(j['left'])+int(j['width']))):
							if(top==int(j['top']) and (left+left_thresh)<int(j['left'])):
								row.append(j)
								left = int(j['left'])
		if len(row)==num_cols:
			columns = [k['text'].strip() for k in row]
			return columns
	return []

def fix_image_lines(image_lines):
	'''part 2 of algorithm, fix data structure to force Python line index to equal line_num
	   		-- force digits to be after words (TODO: flawed logic, should be ordered left to right)
	'''
	max_line_num = max([i['line_num'] for i in image_lines[-1]])
	temp_list = [[] for i in range(0,max_line_num+1)]
	for i in range(0,len(image_lines)):
		for j in range(0,len(image_lines[i])):
			temp_list[image_lines[i][j]['line_num']].append(image_lines[i][j])
	return temp_list

def save_image_data(image_data):
	'''save cleaned data from OCR program
	'''
	columns = ['text','line_num','left','top','width','height']
	data_dict = {i:[] for i in columns}
	for i in range(0,len(image_data['text'])):
		if(image_data['text'][i] not in ('',' ',None,'$','§')):
			image_data['text'][i] = image_data['text'][i].replace("A4","4").replace("G4","34").replace("G6","36")
			if(len(image_data['text'][i].strip())>1):
				if("." in image_data['text'][i] and image_data['text'][i].replace("(","").replace(")","").replace("0.","").replace(".","").replace(",","").strip().isdigit()):
					if(image_data['text'][i].strip()[0]!="0"):
						image_data['text'][i] = image_data['text'][i].replace(".",",")
			if(image_data['text'][i][0]=="0"):
				image_data['text'][i] = "0." + image_data['text'][i][1:]
			for key in columns:
				data_dict[key].append(str(image_data[key][i]))
	print('Dumping '+ str(len(data_dict['text'])) + " rows into SQL...") #how long is the dict we're getting out?
	dict_to_sqlite(data_dict,'image_data')
	return

def preprocess_image(filename):
	'''get rid of horizontal lines in the financial statement (interfears with OCR)
	'''
	img = cv2.imread(filename)
	img = cv2.resize(img, None, fx=1.2, fy=1.2, interpolation=cv2.INTER_CUBIC)
	img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
	kernel = np.ones((1, 1), np.uint8)
	img = cv2.dilate(img, kernel, iterations=1)
	img = cv2.erode(img, kernel, iterations=1)
	lns = cv2.ximgproc.createFastLineDetector(length_threshold=18).detect(img)
	if lns is not None:
		for ln in lns:
			(x_start, y_start, x_end, y_end) = [int(i) for i in ln[0]]
			if(abs(abs(float(y_start))-abs(float(y_end)))<5):
				cv2.line(img, (x_start-(x_end-x_start), y_start+2), (x_end+2, y_end+2), (255, 255, 255), thickness=6)
	return img

def get_image_data(img):
	filename = str(os.path.abspath(os.path.dirname( __file__ ))+"\\temp\{}.png").format(os.getpid())
	cv2.imwrite(filename, img)
	image_data = image_to_data(filename, config='--psm 11', output_type = Output.DICT)
	return image_data, filename

def clean_numbers(data):
	'''turn dashes into zeros, reposition dashes so that the "top" value isn't so different from other numbers
	'''
	for i in range(0,len(data)):
		if(data[i]['text'].strip()==b'\xe2\x80\x94'.decode('utf-8')):
			data[i]['text'] = str(0)
			data[i]['top'] = float(data[i]['top']) - 10
		elif(data[i]['text'].strip()[0]=="(" and data[i]['text'].strip()[-1]==")"):
			if(data[i]['text'].replace("(","").replace(")","").replace("0.","").replace(".","").replace(",","").strip().isdigit()):
				data[i]['text'] = str("—" + data[i]['text'][1:-1])
		data[i]['top'] = int(data[i]['top'])
		data[i]['left'] = int(data[i]['left'])
		data[i]['width'] = int(data[i]['width'])
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
					new_data[i][j]['text'] = month
					passed = 1
					break
			if(passed==1):
				try:
					if(new_data[i][j+1]['text'].strip().replace(",","").isdigit() and new_data[i][j+2]['text'].strip().replace(",","").isdigit()):
						possible_dates.append([new_data[i][j], new_data[i][j+1], new_data[i][j+2]])
					else:
						raise Exception("Skip to next try...")
				except:
					try:
						if(new_data[i][j+1]['text'].strip().replace(",","").isdigit()):
							possible_dates.append([new_data[i][j], new_data[i][j+1]])
						else:
							possible_dates.append([new_data[i][j]])
					except:
						possible_dates.append([new_data[i][j]])
		if(len(possible_dates)==num_cols):
			break
	if(len(possible_dates)!=num_cols):
		return None
	entertain_data = [i for i in new_data if int(i[0]['top'])>int(possible_dates[0][0]['top']) and int(i[0]['top'])<=int(possible_dates[0][0]['top'])+50]
	entertain_data = [item for sublist in entertain_data for item in sublist]
	if(len(possible_dates)==num_cols):
		if(len(possible_dates[0])==2):
			for i in range(0,len(possible_dates)):
				surface_1 = [int(possible_dates[i][0]['left']), int(possible_dates[i][-1]['left'])+int(possible_dates[i][-1]['width'])]
				for j in range(0,len(entertain_data)):
					surface_2 = [int(entertain_data[j]['left']), int(entertain_data[j]['left'])+int(entertain_data[j]['width'])]
					if((surface_2[0]>=surface_1[0] and surface_2[0]<=surface_1[1]) or (surface_1[0]>=surface_2[0] and surface_1[0]<=surface_2[1])):
						try:
							number_below = int(entertain_data[j]['text'].strip().replace(",",""))
							if(number_below>=1969 and number_below<=2022):
								possible_dates[i].append(entertain_data[j])
						except:
							pass
	if(len(possible_dates)==num_cols):
		return possible_dates
	else:
		return None

def scrape_financials(image_data, page_num):
	'''scrapes financial data from chosen set of images
	'''
	save_image_data(image_data) #throw into SQL
	SQL = """select * from image_data where text<>'' and text is not null and text<>' ';"""
	image_data = list_to_dict(clean_numbers(run_SQL(SQL)))
	# start of my hairbrained image_lines scheme
	image_lines = [[{key: image_data[key][0] for key in ('text','top','left','width')}]]
	image_lines[0][0]['line_num'] = 0
	tack_on = []
	line_num = 1
	for i in range(0,len(image_data['text'])):
		if image_data['left'][i]<300: # define how far out the start of a line can be
			if(image_data['top'][i]>image_lines[len(image_lines)-1][0]['top']+5):
				line = {key: image_data[key][i] for key in ('text','top','left','width','line_num')}
				line['line_num'] = line_num
				line_num+=1
				image_lines.append([line])
			else:
				tack_on.append({key: image_data[key][i] for key in ('text','top','left','width','line_num')})
		else:
			tack_on.append({key: image_data[key][i] for key in ('text','top','left','width','line_num')})
	tack_on = sorted(tack_on, key = lambda num: num['top'], reverse=True)
	for i in tack_on:
		image_lines[-1].append(i)
	max_line_num = len(image_lines)-1
	for i in range(0,len(image_lines[-1])):
		image_lines[-1][i]['line_num'] = max_line_num

	# group data into lines, sort left to right
	for i in range(0,100):	
		image_lines, passed = group_by_lines(image_lines)
		image_lines = fix_image_lines(image_lines)
		if(passed==0):
			break
	for i in range(0,len(image_lines)):
		image_lines[i] = sorted(image_lines[i], key = lambda var: var['left'])

	top_data = image_lines[0]+image_lines[1]

	for i in range(0,len(image_lines)):
		top_list = [k['top'] for k in image_lines[i]]
		top_range = [min(top_list),max(top_list)]
		image_lines[i] = {'text': [k['text'].replace("$","").replace(",","").strip().lower() for k in image_lines[i] if len(k['text'].replace("$","").strip().lower())>0],
							'top': top_range, 'page_num': str(page_num+1)}

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
		
	num_cols = most_frequent([len(i['values']) for i in image_lines if len(i['values'])>0])
	num_rows = len(image_lines)
	print(str(num_rows) + " rows and " + str(num_cols) + " columns being initialized:")
	potential_dates = detect_dates(top_data, num_cols)
	columns = []
	if(potential_dates):
		for row in potential_dates:
			print(" ".join([i['text'] for i in row]))
		for i in potential_dates:
			column = " ".join([j['text'] for j in i])
			columns.append(column)

	# bring in page number and line number
	SQL = """drop table if exists image_data_1;"""
	run_SQL(SQL, commit_indic='y')
	SQL = """
		create table image_data_1 as
		select cast(left as 'decimal') as left, text, cast(top as 'decimal') as top, cast(width as 'decimal') as width,
		case
		"""
	for i in range(0,len(image_lines)):
		top_range = image_lines[i]['top']
		SQL += " when cast(top as 'decimal') between " + str(top_range[0]) + " and " + str(top_range[1]) + " then " + str(i) + "\n"
	SQL += """ 
		end as line_num, """ + str(image_lines[0]['page_num']) + """ as page_num
		from image_data;
		"""
	run_SQL(SQL, commit_indic='y')

	# bring in variable names (1:1 with line_num)
	SQL = """select * from image_data_1 where line_num is not null;"""
	data = run_SQL(SQL)
	for i in range(0,len(data)):
		for j in range(0,len(image_lines)):
			if(int(data[i]['line_num'])==j):
				data[i]['variable'] = image_lines[j]['variable']
	for i in range(0,len(data)):
		if("," in data[i]['text']):
			if(len(data[i]['text'][data[i]['text'].index(','):].replace(")","").replace(",",""))<3):
				data[i]['text'] = data[i]['text'].replace(",",".")
		if(len(data[i]['text'].strip())>=3):
			if("0," in data[i]['text'].replace("(","")[0:2]):
				data[i]['text'] = data[i]['text'].replace("0,",".")
		data[i]['text'] = data[i]['text'].replace("..",".").replace(".,",".").replace(",.",".").replace(",","")
				
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"image_data_2")

	# cut off stuff on the far left of the page
	SQL = """drop table if exists image_data_3;"""
	run_SQL(SQL, commit_indic='y')
	SQL = """
		create table image_data_3 as
		select *
		from image_data_2
		where text not in ('$',' ', 'S$','§')
		and cast(left as 'decimal')>(select max(cast(left as 'decimal'))/4 from image_data_2);
		"""
	run_SQL(SQL, commit_indic='y')

	# remove stuff that's floating (not in a column)
	SQL = """select * from image_data_3 order by cast(left as 'decimal') asc;"""
	data = run_SQL(SQL)
	data = implement_left_rule(data)
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"image_data_4")

	# remove non-numeric data below a certain threshold on the page
	SQL = """select * from image_data_4;"""
	data = run_SQL(SQL)
	high_top = [i['top'] for i in sorted(data, key=lambda row: int(row['top']))]
	high_top = int(high_top[int(len(high_top)/2)])
	data = [i for i in data if i['text'].replace(",","").replace("$","").replace("(","").replace(")","").replace(" ","").replace("-","").replace("0.","").strip().lower().replace(".","").isdigit() or int(i['top'])<=high_top]
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"image_data_5")

	# if there's a top discrepancy past a certain threshold boot from the line_num
	SQL = """select * from image_data_5;"""
	data = run_SQL(SQL)
	for i in range(0,len(data)):
		line_num = data[i]['line_num']
		current_top = int(data[i]['top'])
		min_top = min([int(j['top']) for j in data if j['line_num']==line_num])
		if(abs(current_top-min_top)>20):
			data[i]['line_num'] = str(int(data[i]['line_num']) + 420)
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"image_data_6")

	# part 2 of removing floating data
	data = run_SQL("select * from image_data_6;")
	isolated = []
	for i in range(0,69):
		data, passed, isolated = isolate_whitespace(data, num_rows, isolated)
		if(passed==0):
			break
	isolated = sorted(isolated, key = lambda row: int(row['top']), reverse=False)
	if(len(isolated)>0):
		dict_to_sqlite(list_to_dict(isolated),"garbage")
	else:
		run_SQL("delete from garbage;",commit_indic='y')
	dict_to_sqlite(list_to_dict(data),"image_data_7")

	# throw out lines where # of data points exceeds # columns
	SQL = """
	insert into garbage
	select * from image_data_7 where line_num in (
	select distinct line_num from (
	select distinct line_num, count(*) as count 
	from image_data_7
	group by line_num 
	order by count(*) asc)
	where count>"""+str(num_cols)+""")
	or text not GLOB '*[0-9]*'
	or cast(line_num as 'decimal')>=420;
	"""
	run_SQL(SQL, commit_indic='y')
	SQL = """
	select a.* 
	from image_data_7 a
	left join garbage b
	on a.line_num=b.line_num and a.left=b.left and a.text=b.text
	where b.line_num is null;
	"""
	dict_to_sqlite(list_to_dict(run_SQL(SQL)),"image_data_8")

	# part 3 of removing floating data
	SQL = """select * from image_data_8 order by cast(left as 'decimal') asc;"""
	data = run_SQL(SQL)
	data = implement_left_rule(data)
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"image_data_9")

	# bring in column numbers
	SQL = """select distinct text, left, top from image_data_9 order by cast(left as 'decimal') asc;"""
	data = run_SQL(SQL)
	results = [0] + detect_gaps(data)
	SQL = """drop table if exists image_data_10;"""
	run_SQL(SQL, commit_indic='y')
	SQL = """
		create table image_data_10 as
		select distinct variable, text, left, top, width, line_num, page_num, case
		"""
	counter = 1
	for i in range(0,len(results)-1):
		SQL += " when cast(left as 'decimal') between " + str(results[i]) + " and " + str(results[i+1]) + " then "+str(counter)
		counter+=1
	SQL += " when cast(left as 'decimal')>=" + str(results[-1]) + " then "+str(counter)
	SQL += """ end as col_num
		from image_data_9;
		"""
	run_SQL(SQL, commit_indic='y')

	# force top value to be constant for each line
	SQL = """
		select distinct a.line_num, min(a.top) as top
		from image_data_10 a
		inner join image_data_9 b
		on a.line_num=b.line_num and a.top<>b.top;
		"""
	data = run_SQL(SQL)
	data = [i for i in data if i['line_num'] is not None]
	for i in data:
		conditional = "where line_num=" + str(i['line_num'])
		update_in_table("image_data_10", "top", str(i['top']), conditional)

	# bring in column names
	data = run_SQL("select * from image_data_10 order by cast(top as 'decimal') asc, cast(left as 'decimal');")	
	if(len(columns)==0):
		garbage = run_SQL("select * from garbage order by cast(top as 'decimal'), cast(left as 'decimal');")
		columns = get_column_names(garbage, num_cols, int(high_top))
	if(len(columns)==0):
		columns = [i['text'] for i in data[0:num_cols]]
		data = data[num_cols:]
	print("_______________Final Column Defs: " + ", ".join(columns) + " _______________")
	for i in range(0,len(data)):
		data[i]['column'] = columns[(int(data[i]['col_num'])-1)]
	data = clean_numbers(data)
	data_dict = list_to_dict(data)
	dict_to_sqlite(data_dict,"image_data_11")

	# final table of clean data
	SQL = """drop table if exists image_data_12;"""
	run_SQL(SQL, commit_indic='y')
	SQL = """
		create table image_data_12 as
		select distinct variable, cast(replace(text,'—','-') as 'decimal') as value, column, cast(page_num as 'decimal') as page_num,
		cast(line_num as 'decimal') as line_num, cast(col_num as 'decimal') as col_num, cast(top as 'decimal') as top,
		cast(left as 'decimal') as left, cast(width as 'decimal') as width
		from image_data_11;
		"""
	run_SQL(SQL, commit_indic='y')
	SQL = """
	insert into financials
	select * from image_data_12;
	"""
	run_SQL(SQL, commit_indic='y')

#============================ START OF MAIN LOGIC ============================#
Tk().withdraw()
filename = filedialog.askopenfilename() #filename = 'C:\\Users\\micha\\Desktop\\financial statement reader\\test - Tesla\\e9f7bb6a-f6b7-4b3d-beec-afdcb2f9e644-4.ppm' #manual for testing
start_time = time.time()

# if it's a PDF, convert to image first
try:
	images = pdf_to_image(filename)
	print("PDF selected...")
except:
	print("IMAGE selected...")
	images = [filename]

# clear out results table
SQL = """delete from financials;"""
run_SQL(SQL, commit_indic='y')

# scrape financials from each image
for page_num in range(0,len(images)):
	old_image = images[page_num]
	img = preprocess_image(old_image)
	time_a = time.time()
	image_data, image = get_image_data(img)
	print("Time taken to get image data from OCR: " + str(round(time.time()-time_a,2)) + " seconds!")
	#show_boxes(image_data, image)
	#import sys
	#sys.exit(0)
	os.remove(image)
	if(len(images))>1:
		os.remove(old_image)
	scrape_financials(image_data, page_num)

output_results()
print("finished running in: " + str(time.time()-start_time) + " seconds")

