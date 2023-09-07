from flask import Flask, jsonify, render_template
import pandas as pd
import os
import json
from shapely.geometry import Point, shape, Polygon
from concurrent.futures import ThreadPoolExecutor, as_completed
import glob
from rtree import index as rtree_index
from collections import Counter
from fuzzywuzzy import process  # Add this import at the top of your file
from dotenv import load_dotenv
load_dotenv()


api_key = os.getenv("GOOGLE_MAPS_API_KEY")



app = Flask(__name__, static_folder=".", static_url_path='')

borough_metrics = {}
ward_metrics = {}
ward_data = {}

# Load ward data into memory
with open("borough_ward_coordinates.json", "r") as f:
    ward_data = json.load(f)

# Debug print to display the keys in ward_data
print("Debug: Ward names in ward_data:", list(ward_data.keys()))

# Load borough data into memory
with open("london_boroughs.json", "r") as f:
    borough_data = json.load(f)

def read_and_process_csv_borough(csv_file_path):
    temp_df = pd.read_csv(csv_file_path)
    temp_df.dropna(subset=['Latitude', 'Longitude'], inplace=True)
    return temp_df.sample(frac=0.01)

def initialize_ward_metrics():
    print("Initializing ward metrics...")
    
    # Initialize an empty DataFrame to hold the merged data
    merged_df = pd.DataFrame()
    
    # Define the path to the main 'data' folder
    main_folder_path = './data'
    
    # Use glob to find all CSV files under the main 'data' folder
    all_csv_files = glob.glob(f"{main_folder_path}/*/*.csv")
    
    for csv_file in all_csv_files:
        try:
            temp_df = read_and_process_csv_borough(csv_file)
        except Exception as exc:
            print(f"{csv_file} generated an exception: {exc}")
        else:
            merged_df = pd.concat([merged_df, temp_df], ignore_index=True)
    
    # Sample 1% of the DataFrame
    sampled_df = merged_df.sample(frac=0.01)
    
    wardCrimeCounts = {}
    
    # Loop through each ward and count crimes based on the sampled data
    for borough, wards in ward_data.items():
        for ward, coordinates in wards.items():
            polygon = Polygon(coordinates)
            
            ward_df = sampled_df[sampled_df.apply(lambda row: polygon.contains(Point(row['Longitude'], row['Latitude'])), axis=1)]
            
            # Normalize borough and ward names: lowercase and remove spaces
            normalized_ward = ward.lower().replace(" ", "")
            
            # Fuzzy matching to find the closest matching normalized_ward
            if wardCrimeCounts:  # Check if wardCrimeCounts is not empty
                best_match, score = process.extractOne(normalized_ward, wardCrimeCounts.keys())
                
                # If the match score is above a threshold (e.g., 80), consider it a match
                if score > 80:
                    normalized_ward = best_match
            
            # Count crimes for this ward based on the sampled data
            wardCrimeCounts[normalized_ward] = wardCrimeCounts.get(normalized_ward, 0) + len(ward_df)

            calculate_ward_metrics(wardCrimeCounts)  # Uncomment this when you integrate the function
            print("Ward metrics initialized.")


def initialize_borough_metrics():
    global borough_metrics
    if not borough_metrics:
        print("Initializing borough metrics...")
        
        merged_df = pd.DataFrame()
        main_folder_path = './data'
        all_csv_files = glob.glob(f"{main_folder_path}/*/*.csv")
        
        # Loop through each CSV file to read and process it
        for csv_file in all_csv_files:
            try:
                temp_df = read_and_process_csv_borough(csv_file)
            except Exception as exc:
                print(f"{csv_file} generated an exception: {exc}")
            else:
                merged_df = pd.concat([merged_df, temp_df], ignore_index=True)
        
        # Sample 1% of the DataFrame
        sampled_df = merged_df.sample(frac=0.01)
        
        # Load borough geometries
        with open("london_boroughs.json", "r") as f:
            boroughs_data = json.load(f)
        
        borough_geometries = {}
        for feature in boroughs_data['features']:
            borough_name = feature['properties']['name']
            polygon = shape(feature['geometry'])
            borough_geometries[borough_name] = polygon
        
        boroughCrimeCounts = {}
        
        # Populate boroughCrimeCounts based on sampled_df
        for index, row in sampled_df.iterrows():
            point = Point(row['Longitude'], row['Latitude'])
            for borough, polygon in borough_geometries.items():
                if polygon.contains(point):
                    if borough not in boroughCrimeCounts:
                        boroughCrimeCounts[borough] = 0
                    boroughCrimeCounts[borough] += 1
                    break  # Exit the loop once a containing borough is found
        
        calculate_borough_metrics(boroughCrimeCounts)
        print("Borough metrics initialized.")

  
def calculate_borough_metrics(boroughCrimeCounts):
    global borough_metrics
    borough_metrics = {}
    
    # Sort boroughs by crime count to get the ranking
    sorted_boroughs = sorted(boroughCrimeCounts.items(), key=lambda x: x[1], reverse=True)
    
    # Assign rankings and determine risk level
    for rank, (borough, count) in enumerate(sorted_boroughs, 1):
        if rank <= 5:
            risk_level = "High"
            safety_status = "Not Safe"
        elif rank <= 10:
            risk_level = "Medium"
            safety_status = "Moderate"
        else:
            risk_level = "Low"
            safety_status = "Safe"

        borough_metrics[borough] = {
            'Risk Level': risk_level,
            'Ranking': rank,
            'Safety Status': safety_status
        }

def calculate_ward_metrics(wardCrimeCounts):
    global ward_metrics
    ward_metrics = {}
    
    # Sort wards by crime count to get the ranking
    sorted_wards = sorted(wardCrimeCounts.items(), key=lambda x: x[1], reverse=True)
    
    # Assign rankings and determine risk level
    for rank, (ward, count) in enumerate(sorted_wards, 1):
        if rank <= 5:
            risk_level = "High"
            safety_status = "Not Safe"
        elif rank <= 10:
            risk_level = "Medium"
            safety_status = "Moderate"
        else:
            risk_level = "Low"
            safety_status = "Safe"

        ward_metrics[ward] = {
            'Risk Level': risk_level,
            'Ranking': rank,
            'Safety Status': safety_status
        }

def calculate_ward_crime_counts():
    global ward_metrics  # Assuming ward_metrics also contains the crime counts
    return ward_metrics

@app.route('/')
def index():
    return render_template('map.html', api_key=api_key)

@app.route('/london_boroughs.json')
def get_boroughs():
    with open("london_boroughs.json", "r") as f:
        boroughs_data = json.load(f)
    return jsonify(boroughs_data)

@app.route('/get_borough_metrics')
def get_borough_metrics():
    if not borough_metrics:
        print("borough_metrics is empty or None")
        return jsonify({"error": "borough_metrics not initialized"}), 500
    return jsonify(borough_metrics)

# New endpoint to get ward metrics
@app.route('/get_ward_metrics')
def get_ward_metrics():
    global ward_metrics  # Declare it as global if it's a global variable
    return jsonify(ward_metrics)

@app.route('/get_ward_crime_counts')
def get_ward_crime_counts():
    counts = calculate_ward_crime_counts()
    return jsonify(counts)

@app.route('/get_heat_data')
def get_heat_data():
    # Initialize an empty DataFrame to hold the merged data
    merged_df = pd.DataFrame()

    # Define the path to the main 'data' folder
    main_folder_path = './data'

    # Loop through each subfolder in the main 'data' folder
    for month_folder in os.listdir(main_folder_path):
        month_folder_path = os.path.join(main_folder_path, month_folder)

        # Check if it's a folder
        if os.path.isdir(month_folder_path):

            # Loop through each CSV file in the month's folder
            for csv_file in os.listdir(month_folder_path):
                if csv_file.endswith('.csv'):
                    csv_file_path = os.path.join(month_folder_path, csv_file)

                    # Read the CSV file into a DataFrame
                    temp_df = pd.read_csv(csv_file_path)

                    # Drop rows with NaN in 'Latitude' and 'Longitude'
                    temp_df.dropna(subset=['Latitude', 'Longitude'], inplace=True)

                    # Sample 1% of the DataFrame
                    temp_df = temp_df.sample(frac=0.01)

                    # Append the DataFrame to the merged DataFrame
                    merged_df = pd.concat([merged_df, temp_df], ignore_index=True)

    # Generate heatmap data
    heat_data = [[row['Latitude'], row['Longitude']] for index, row in merged_df.iterrows()]

    return jsonify(heat_data)

@app.route('/get_borough_crime_counts')
def get_borough_crime_counts():
    return jsonify(borough_metrics)
#
if __name__ == '__main__':
    initialize_ward_metrics()
    initialize_borough_metrics()
    app.run(debug=True)