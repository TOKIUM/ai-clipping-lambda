import csv
import json
import os

def compare_json_files(csv_file_path, dir1_path, dir2_path, output_csv_path):
    results = []
    header = ["uuid", "file_name", "field_name", "delta_x_cordinate", "delta_y_cordinate", "delta_width", "delta_height"]
    results.append(header)

    with open(csv_file_path, 'r', encoding='utf-8') as f_csv:
        reader = csv.DictReader(f_csv)
        for row in reader:
            file_name_pdf = row.get("ファイル名")
            if not file_name_pdf:
                print(f"Skipping row due to missing 'ファイル名': {row}")
                continue

            uuid = os.path.splitext(file_name_pdf)[0]
            json_file_name = f"{uuid}_output.json" # Corrected to match user specification
            
            uuid2 = row.get("UUID")
            print(f"UUID2: {uuid2}")
            json_file_name2 = f"{uuid2}.json" # Corrected to match user specification

            file1_path = os.path.join(dir1_path, json_file_name)
            file2_path = os.path.join(dir2_path, json_file_name2)

            data1_clips = {}
            data2_clips = {}

            if os.path.exists(file1_path):
                try:
                    with open(file1_path, 'r', encoding='utf-8') as f1:
                        data1 = json.load(f1)
                        for clip in data1.get("clips", []):
                            data1_clips[clip["field_name"]] = clip
                except json.JSONDecodeError:
                    print(f"Error decoding JSON from {file1_path}")
                    # Optionally, treat as if file doesn't exist or has no clips
                    pass # Or handle more gracefully
                except Exception as e:
                    print(f"Error reading {file1_path}: {e}")
                    pass


            if os.path.exists(file2_path):
                try:
                    with open(file2_path, 'r', encoding='utf-8') as f2:
                        data2 = json.load(f2)
                        for clip in data2.get("clips", []):
                            data2_clips[clip["field_name"]] = clip
                except json.JSONDecodeError:
                    print(f"Error decoding JSON from {file2_path}")
                    pass
                except Exception as e:
                    print(f"Error reading {file2_path}: {e}")
                    pass

            all_field_names = set(data1_clips.keys()) | set(data2_clips.keys())

            if not all_field_names: # If both files are missing or empty
                if not os.path.exists(file1_path) and not os.path.exists(file2_path):
                    print(f"Both JSON files not found for UUID {uuid}: {file1_path}, {file2_path}")
                elif not data1_clips and not data2_clips:
                     print(f"No clips found in either JSON file for UUID {uuid}")
                # else: # one of them existed but was empty or unreadable
                    # errors already printed above

            for field_name in all_field_names:
                clip1 = data1_clips.get(field_name, {})
                clip2 = data2_clips.get(field_name, {})

                # Get values, defaulting to 0 if key is missing or clip is empty
                x1 = clip1.get("x_coordinate", 0)
                y1 = clip1.get("y_coordinate", 0)
                w1 = clip1.get("width", 0)
                h1 = clip1.get("height", 0)

                x2 = clip2.get("x_coordinate", 0)
                y2 = clip2.get("y_coordinate", 0)
                w2 = clip2.get("width", 0)
                h2 = clip2.get("height", 0)

                delta_x = x1 - x2
                delta_y = y1 - y2
                delta_w = w1 - w2
                delta_h = h1 - h2

                results.append([uuid2, json_file_name, field_name, delta_x, delta_y, delta_w, delta_h])

    with open(output_csv_path, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.writer(outfile)
        writer.writerows(results)
    print(f"Comparison finished. Output saved to {output_csv_path}")

if __name__ == "__main__":
    csv_file = "/Users/satoshusuke/Documents/tokium/ai-clipping-lambda/data/clipping_0521.csv"
    output_jsons_dir = "/Users/satoshusuke/Documents/tokium/ai-clipping-lambda/output_jsons"
    output_jsons_worker_dir = "/Users/satoshusuke/Documents/tokium/ai-clipping-lambda/output_jsons_worker"
    output_diff_csv = "/Users/satoshusuke/Documents/tokium/ai-clipping-lambda/diff_output.csv"

    # Ensure output directories for JSON files exist, though script primarily reads from them
    # For this script, it's more about ensuring the input dirs are correct.
    # os.makedirs(output_jsons_dir, exist_ok=True)
    # os.makedirs(output_jsons_worker_dir, exist_ok=True)

    compare_json_files(csv_file, output_jsons_dir, output_jsons_worker_dir, output_diff_csv)