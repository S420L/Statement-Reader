import os
import tempfile
import time
from tkinter.filedialog import askopenfilename

import cv2
import pandas as pd
import pytesseract as Tessa
from pdf2image import convert_from_path
from PIL import Image
from pytesseract import Output

from tricks import dict_to_sqlite, run_SQL

pd.options.mode.chained_assignment = None  # default='warn'

#get text from image
def image_to_text(filename):
	image = cv2.imread(filename)
	gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
	filename = str(os.path.abspath(os.path.dirname(__file__))+"/pics_and_pdfs/{}.png").format(os.getpid())
	cv2.imwrite(filename, gray)
	image_text = Tessa.image_to_string(Image.open(filename))
	image_data = Tessa.image_to_data(filename, output_type = Output.DICT)
	os.remove(filename)
	#for i in range(0,len(image_data['line_num'])):
	#	(x, y, w, h) = (image_data['left'][i], image_data['top'][i], image_data['width'][i], image_data['height'][i])
	#	cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
	#cv2.imshow('Results',image)
	#cv2.waitKey(0)
	return image_text, image_data

#get image from PDF
def pdf_to_image(filename):
	with tempfile.TemporaryDirectory() as path:
		images_from_path = convert_from_path(filename, output_folder=os.path.abspath(os.path.dirname(__file__))+"/pics_and_pdfs")
		print('running for image: ' + str(images_from_path))
		filenames = [i.filename for i in images_from_path]
		return filenames

def group_by_lines_up(image_lines):
	passed = 0
	for i in range(0,len(image_lines)):
		for j in range(0,len(image_lines[i])):
			first_top = image_lines[i][0]['top']
			if(image_lines[i][j]['top']>first_top+5):
				if(image_lines[i][j]['text'].replace(",","").replace("$","").replace("(","").replace(")","").replace(" ","").strip().lower().isdigit()):
					if(image_lines[i][j]['line_num']<len(image_lines)-1):
						image_lines[i][j]['line_num'] += 1
						passed = 1
					else:
						image_lines[i][j]['text'] = "" #terminate journey of this number, its probably from the bottom of the sheet
	return image_lines, passed

def group_by_lines_down(image_lines):
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

def fix_image_lines(image_lines):
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
			if(j['text'].replace(",","").replace("$","").replace("(","").replace(")","").replace(" ","").strip().lower().isdigit()):
				second_half.append(j)
			else:
				first_half.append(j)
		return_list.append(first_half+second_half)
	return return_list

def get_color(image_data, d):
	return_dict = {'level':[],'left':[],'top':[],'width':[],'height':[],'text':[],'R':[], 'G':[], 'B':[],'count':[],'percent':[]} 
	for w in range(0,len(d['left']),1):
		pixel_list = []
		for i in range(d['left'][w],d['left'][w]+d['width'][w],1):
			pixel_list.append(image_data[d['top'][w]+(int(d['height'][w]/2))][i]) #sample pixels in a line through the middle of each box
		pixel_list = [i for i in pixel_list if int(i[0]) + int(i[1]) + int(i[2]) < 742] #disregard anything that's basically white
		pixel_list = [[int(i[0]),int(i[1]),int(i[2])] for i in pixel_list]
		if(len(pixel_list)>0 and d['text'][w]!=''): #only run for boxes with words in them
			df = pd.DataFrame.from_records(pixel_list) #turn dict into dataframe
			df.columns = ['B','G','R'] #this library reverses the rgb order
			df = df.groupby(['B','G','R']).size().reset_index().rename(columns={0:'count'}) #on the equator of the box, we want to see how many of each (non-white) color show up 
			df['percent'] = df['count']/df['count'].sum() #get % of pixels on the center line that are that color
			final_row = df[df['count']==df['count'].max()]
			#print(final_row)
			#print("text ^^: " + str(d['text'][w]))
			if(len(final_row['count'])>1): #force it to be distinct
				final_row['R'] = int(final_row['R'].sum()/len(final_row)) #avg the colors
				final_row['G'] = int(final_row['G'].sum()/len(final_row)) 
				final_row['B'] = int(final_row['B'].sum()/len(final_row))
				final_row['count'] = int(final_row['count'].max()) #take the max count
				final_row['percent'] = float(final_row['percent'].max())
				final_row = final_row.drop_duplicates()
			final_row = final_row.to_dict('series')
			return_dict['level'].append(str(d['level'][w]))  #add variables that didn't change
			return_dict['left'].append(str(d['left'][w]))
			return_dict['top'].append(str(d['top'][w]))
			return_dict['width'].append(str(d['width'][w]))
			return_dict['height'].append(str(d['height'][w]))
			return_dict['text'].append(str(d['text'][w]))
			return_dict['R'].append(str(final_row['R'].values[0]))  #add variables that were generated in this function
			return_dict['G'].append(str(final_row['G'].values[0]))
			return_dict['B'].append(str(final_row['B'].values[0]))
			return_dict['count'].append(str(final_row['count'].values[0]))
			return_dict['percent'].append(str(final_row['percent'].values[0]))
	return return_dict

#gui
#Tk().withdraw()
#filename = askopenfilename()
filename = os.path.abspath(os.path.dirname( __file__ ))+'/pics_and_pdfs/dd70d073-44fe-4814-a9f2-adcc2c7fa3f3-2.ppm' #manual for testing

"""image_data = cv2.imread(filename,1) #get color of whatever we're looking at
img = cv2.imread(filename)
d = Tessa.image_to_data(img, output_type = Output.DICT)
print('LEN D: ' + str(len(d['left']))) #how long is the dict we're putting into function?
box_dict = get_color(image_data,d) #get RGB info on characters
print('LEN box_dict:: '+ str(len(box_dict['R']))) #how long is the dict we're getting out?
print(box_dict.keys())

dict_to_sqlite(box_dict,'image_table', 'image_data.db')"""

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
	image_text, image_data = image_to_text(image)
	full_image_data.append(image_data) #only use image data (includes text)

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
	for i in image_lines:
		print(i[0]['text'])
		print(i[0]['line_num'])

	"""line_nums = sorted(list(set(image_data['line_num'])),key=lambda num: num, reverse=False)
	for i in range(0,len(line_nums)):
		temp_list = []
		for j in range(0,len(image_data['line_num'])):
			if(line_nums[i]==image_data['line_num'][j]):
				data_dict = {'text': image_data['text'][j]}
				data_dict['top'] = image_data['top'][j]
				data_dict['line_num'] = image_data['line_num'][j]
				temp_list.append(data_dict)
		image_lines.append(temp_list)"""

	for i in range(0,len(image_lines)):
		image_lines[i] = [k for k in image_lines[i] if k['text'].strip()!=""]

	for i in range(0,len(image_lines)):
		for j in range(0,len(image_lines[i])):
			if(image_lines[i][j]['text'].strip()==b'\xe2\x80\x94'.decode('utf-8')):
				print("ZERO DETECTED")
				image_lines[i][j]['text'] = str(0)
				image_lines[i][j]['top'] = float(image_lines[i][j]['top']) - 10
			elif(image_lines[i][j]['text'].strip()[0]=="(" and image_lines[i][j]['text'][-1].strip()==")"):
				if(image_lines[i][j]['text'].replace("(","").replace(")","").strip().isdigit()):
					print("NEGATIVE DETECTED")
					image_lines[i][j]['text'] = str("—" + image_lines[i][j]['text'][1:-1])

	original_image_lines = [i for i in image_lines]

	#for i in image_lines:
	#	print(min([j['line_num'] for j in i]))
	#for i in image_lines:
	#	print(len(i))
	#for i in image_lines:
	#	if(len(i)>0):
	#		print(i[0]['text'])

	for i in range(0,100):	
		image_lines, passed = group_by_lines_down(image_lines)
		image_lines = fix_image_lines(image_lines)

	for i in range(0,len(image_lines)):
		image_lines[i] = sorted(image_lines[i], key = lambda var: var['left'], reverse = False)

	print("Passed? " + str(passed))
	print("___________________________________")
	print([i['text'] for i in image_lines[-2]])
	print("___________________________________")
	print([i['text'] for i in image_lines[-1]])

	for i in range(0,len(image_lines)):
		image_lines[i] = [k['text'].replace("$","").replace(",","").strip().lower() for k in image_lines[i] if len(k['text'].replace("$","").replace(",","").strip().lower())>0]
	company_name = "UNKNOWN"
	for i in image_lines:
		for j in range(0,len(i)):
			if 'inc.' in i[j] or 'llc.' in i[j]:
				try:
					company_name = i[j-1]
				except:
					company_name = 'INC AT START OF LINE'
	
	data_dict = {'rank': [],'variable': [], 'year': [], 'value': []}
	years = ['2020','2019','2018'] 
	for i in range(0,len(image_lines)):
		values = []
		variable = ""
		for j in image_lines[i]:
			if(j.isdigit()):
				values.append(j)
			else:
				variable += " " + str(j)
		
		if(len(values)==3 and variable!=""):
			for j in range(0,len(years)):
				data_dict['rank'].append(str(i))
				data_dict['variable'].append(variable.strip().lower())
				data_dict['year'].append(years[j])
				data_dict['value'].append(values[j])

	print("_____Inputting first half______")
	[print(len(data_dict[i])) for i in data_dict.keys()]
	dict_to_sqlite(data_dict, "financials_temp_1", str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))

	"""print([i for i in image_lines[7]])
	image_lines = original_image_lines
	for i in range(0,69):	
		image_lines, passed = group_by_lines_down(image_lines)
		image_lines = fix_image_lines(image_lines)

	print([i for i in image_lines[7]])

	#print(first_image_lines)
	#print("_______________________")
	#print(second_image_lines)

	#image_lines = first_image_lines + [i for i in second_image_lines if i[0]['text'] not in [i[0]['text'] for i in first_image_lines]]
	print("Len Image Lines: " + str(len(image_lines)))

	print("Passed: " + str(passed))
	for i in range(0,len(image_lines)):
		image_lines[i] = [k['text'].replace("$","").replace(",","").strip().lower() for k in image_lines[i] if len(k['text'].replace("$","").replace(",","").strip().lower())>0]
	company_name = "UNKNOWN"
	for i in image_lines:
		for j in range(0,len(i)):
			if 'inc.' in i[j] or 'llc.' in i[j]:
				try:
					company_name = i[j-1]
				except:
					company_name = 'INC AT START OF LINE'
	
	data_dict = {'rank': [],'variable': [], 'year': [], 'value': []}
	years = ['2020','2019','2018'] 
	print(len(image_lines))
	for i in range(0,len(image_lines)):
		values = []
		variable = ""
		for j in image_lines[i]:
			if(j.isdigit()):
				values.append(j)
			else:
				variable += " " + str(j)
		
		if(len(values)==3 and variable!=""):
			for j in range(0,len(years)):
				data_dict['rank'].append(str(i))
				data_dict['variable'].append(variable.strip().lower())
				data_dict['year'].append(years[j])
				data_dict['value'].append(values[j])

	print("_____Inputting second half______")
	[print(len(data_dict[i])) for i in data_dict.keys()]
	dict_to_sqlite(data_dict, "financials_temp_2", str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))"""

	'''SQL = """
	insert into financials
	select *
	from (
	select * from financials_temp_1
	union
	select * from financials_temp_2
	);
	"""
	run_SQL(SQL, commit_indic='y', database=str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))'''

print("finished running in: " + str(time.time()-start_time) + " seconds")
