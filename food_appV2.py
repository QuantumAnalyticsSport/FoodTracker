import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from PIL import Image
import io
import base64
import json
import re
from openai import OpenAI

# --- CONFIGURATION ---
GOOGLE_SHEET_NAME = "Food_database"
CREDENTIALS_FILE = "creds.json"  # Replace with actual credentials file

# --- SET UP GOOGLE SHEETS CONNECTION ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(credentials)
sheet = client.open(GOOGLE_SHEET_NAME).sheet1

# --- INITIALIZE SESSION STATE ---
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "image" not in st.session_state:
    st.session_state["image"] = None
if "base64_image" not in st.session_state:
    st.session_state["base64_image"] = None
if "analysis_result" not in st.session_state:
    st.session_state["analysis_result"] = None

# --- USER AUTHENTICATION ---
st.title("🍽️ Food Analysis App")

st.session_state["user_id"] = st.text_input("Username (ID):")
if not st.session_state["user_id"]:
    st.warning("⚠️ Please enter your ID.")
    st.stop()
else:
    st.success("✅ Authenticated!")

# --- IMAGE UPLOAD OR CAMERA ---
st.header("📷 Upload or Take a Photo")
option = st.radio("Choose an option:", ["Upload Photo", "Take Photo"])

if option == "Upload Photo":
    uploaded_file = st.file_uploader("Upload an image", type=["jpg", "png"])
    if uploaded_file:
        st.session_state["image"] = Image.open(uploaded_file)

elif option == "Take Photo":
    captured_photo = st.camera_input("Take a photo")
    if captured_photo:
        st.session_state["image"] = Image.open(captured_photo)

# --- DISPLAY IMAGE ---
if st.session_state["image"]:
    st.image(st.session_state["image"], caption="Uploaded Image", use_container_width=True)

    # Convert RGBA to RGB (JPEG does not support transparency)
    if st.session_state["image"].mode == "RGBA":
        st.session_state["image"] = st.session_state["image"].convert("RGB")

    # Convert image to Base64
    img_buffer = io.BytesIO()
    st.session_state["image"].save(img_buffer, format="JPEG")
    img_bytes = img_buffer.getvalue()
    st.session_state["base64_image"] = base64.b64encode(img_bytes).decode("utf-8")

# --- OPENAI CLIENT ---
client_openai = OpenAI(st.secrets["openai"]["api_key"])
def extract_macros(response_text):
    """Extracts total calories, protein, carbs, and fat from the text."""
    
    calories_matches = re.findall(r"\*\*Total Calories:\*\*\s*([\d.]+)\s*calories", response_text, re.IGNORECASE)
    protein_matches = re.findall(r"\*\*Total Protein:\*\*\s*([\d.]+)\s*g", response_text, re.IGNORECASE)
    carbs_matches = re.findall(r"\*\*Total Carbohydrates:\*\*\s*([\d.]+)g", response_text, re.IGNORECASE)
    fat_matches = re.findall(r"\*\*Total Fat:\*\*\s*([\d.]+)g", response_text, re.IGNORECASE)

    # Convert extracted values to float or int
    result = {
        "calories": int(calories_matches[-1]) if calories_matches else None,
        "protein": float(protein_matches[-1]) if protein_matches else None,
        "carbs": float(carbs_matches[-1]) if carbs_matches else None,
        "fat": float(fat_matches[-1]) if fat_matches else None
    }

    return result

def analyze_food():
    """Analyzes the food in the uploaded image using OpenAI API."""
    if not st.session_state["base64_image"]:
        st.error("❌ No image found. Please upload an image first.")
        return None

    prompt = """
    Identify the food items on this plate and estimate their weights. 
    Then, calculate the total calories and macronutrient breakdown (carbs, protein, fat).
    add a little text to explain your analysis (be brief, just few words per food item)
    At the end add a "Total" section with total calories, carbs, fat, protein 
    displayed like this 
    **Total Nutrition Summary:**

    - **Total Calories:** (total of calories) calories
    - **Total Carbohydrates :** (total of Carbohydrates)g
    - **Total Fat:** (total of Fat)g
    - **Total Protein:** (total of Protein)g
    """

    response = client_openai.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "You are a nutrition expert analyzing food images."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{st.session_state['base64_image']}"}}
            ]}
        ],
        max_tokens=500
    )

    response_text = response.choices[0].message.content
    st.write(response_text)
    # Try to parse JSON response
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        # Fallback to regex extraction
        result = extract_macros(response_text)
    st.session_state["analysis_result"] = result
    return result


# --- BUTTON TO ANALYZE PLATE ---
if st.button("🔍 Analyze Plate"):
    with st.spinner("Processing..."):
        result = analyze_food()

    if result:
        st.success("✅ Analysis Complete!")
        st.write(f"**Calories:** {result.get('calories', 'N/A')} kcal")
        st.write(f"**Protein:** {result.get('protein', 'N/A')} g")
        st.write(f"**Carbs:** {result.get('carbs', 'N/A')} g")
        st.write(f"**Fat:** {result.get('fat', 'N/A')} g")

# --- DISPLAY PREVIOUS ANALYSIS ---
if st.session_state["analysis_result"]:
    st.subheader("📊 Previous Analysis:")
    st.write(st.session_state["analysis_result"])

# --- SAVE TO GOOGLE SHEETS ---
if st.button("📤 Push to Database"):
    if not st.session_state["analysis_result"]:
        st.error("❌ No analysis data found. Please analyze the image first.")
    else:
        data = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            st.session_state["user_id"],
            st.session_state["analysis_result"].get("calories", "N/A"),
            st.session_state["analysis_result"].get("protein", "N/A"),
            st.session_state["analysis_result"].get("carbs", "N/A"),
            st.session_state["analysis_result"].get("fat", "N/A")
        ]
        sheet.append_row(data)
        st.success("✅ Data pushed to Google Sheets!")

