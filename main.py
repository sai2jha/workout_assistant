import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# =============================================================================
# CUSTOM STYLING
# =============================================================================
st.markdown(
    """
    <style>
    .main {
        background-color: #F5F5F5;
    }
    .bmi-card {
        padding: 1.2rem;
        border-radius: 0.8rem;
        margin-bottom: 1rem;
        text-align: center;
    }
    .bmi-underweight { background-color: #FFF8E1; color: #5D4037; }
    .bmi-normal      { background-color: #E8F5E9; color: #1B5E20; }
    .bmi-overweight  { background-color: #FFF3E0; color: #4E342E; }
    .bmi-obese       { background-color: #FFEBEE; color: #B71C1C; }
    .bmi-card h1, .bmi-card h3, .bmi-card p { color: inherit; }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# ALL DATA FROM Data/Data.txt AND RapidAPI.ipynb
# Flattened into a single exercise pool that the recommender draws from.
# =============================================================================

@st.cache_data
def load_exercise_pool():
    """Load exercise pool from Data/exercises.csv."""
    csv_path = Path(__file__).parent / "Data" / "exercises.csv"
    return pd.read_csv(csv_path)


@st.cache_data
def load_muscle_relationships():
    """
    Build muscle group relationships from workout_creator_dataset.json.
    For each exercise, every muscle in its muscleGroups list is related
    to every other muscle in that list.
    Returns a dict: { "Chest": ["Triceps", "Shoulders"], ... }
    """
    json_path = Path(__file__).parent / "Data" / "workout_creator_dataset.json"
    with open(json_path) as f:
        data = json.load(f)

    relationships = {}
    for exercise in data["exercises"]:
        muscles = exercise.get("muscleGroups", [])
        for muscle in muscles:
            if muscle not in relationships:
                relationships[muscle] = set()
            for other in muscles:
                if other != muscle:
                    relationships[muscle].add(other)

    # Convert sets to sorted lists
    return {k: sorted(v) for k, v in relationships.items()}


# =============================================================================
# SEMANTIC SEARCH — embeddings + cosine similarity
# =============================================================================

@st.cache_resource
def load_embedding_model():
    """Load the sentence-transformer model once and cache it."""
    return SentenceTransformer("all-MiniLM-L6-v2")


def build_exercise_descriptions(df):
    """Create a rich text description for each exercise for embedding."""
    descriptions = []
    for _, row in df.iterrows():
        desc = (
            f"{row['Name']} - {row['Level']} level {row['Goal']} exercise "
            f"for {row['Muscle']} using {row['Equipment']}. "
            f"Difficulty: {row['Difficulty']}"
        )
        descriptions.append(desc)
    return descriptions


@st.cache_data
def compute_exercise_embeddings(_model, descriptions):
    """Compute embeddings for all exercise descriptions (cached)."""
    return _model.encode(descriptions)


def semantic_search(query, pool_df, model, embeddings, related_map, n=5):
    """Return top-n exercises most similar to the user's natural language query.
    Uses muscle relationships from workout_creator_dataset.json to filter results."""
    query_embedding = model.encode([query])
    similarities = cosine_similarity(query_embedding, embeddings)[0]
    pool_df = pool_df.copy()
    pool_df["_similarity"] = similarities

    # Map common search terms to muscle group names
    # (needed because users type "tricep" not "Triceps")
    keyword_to_muscle = {
        "bicep": "Biceps",
        "tricep": "Triceps",
        "shoulder": "Shoulders",
        "chest": "Chest",
        "back": "Back",
        "leg": "Legs",
        "ab": "Abs",
        "core": "Abs",
    }

    # Detect muscle keyword in query
    query_lower = query.lower()
    detected_muscle = None
    for keyword, muscle_name in keyword_to_muscle.items():
        if keyword in query_lower:
            detected_muscle = muscle_name
            break

    if detected_muscle:
        # Only show exercises for the exact muscle group searched
        filtered = pool_df[pool_df["Muscle"] == detected_muscle]
        results = (
            filtered
            .sort_values("_similarity", ascending=False)
            .drop_duplicates(subset="Name", keep="first")
            .head(n)
        )
    else:
        # No muscle keyword detected — return pure similarity results
        results = (
            pool_df
            .sort_values("_similarity", ascending=False)
            .drop_duplicates(subset="Name", keep="first")
            .head(n)
        )
    return results


# =============================================================================
# RECOMMENDATION ENGINE — scores every dataset exercise for the user
# =============================================================================

def recommend_exercises(pool_df, user_level, user_goal, user_muscle, related_map, n=5):
    """
    Score each exercise in the dataset pool and return the top-n.
    Uses muscle relationships loaded from workout_creator_dataset.json.

    Scoring (higher = better match):
      +3  exact level match
      +2  level is one step away
      +3  exact goal match
      +1  goal is in same family (strength/muscle gain  or  endurance/weight loss)
      +4  exact muscle group match
      +1  baseline for every exercise (so there's always a result)
    """
    level_order = {"Beginner": 0, "Intermediate": 1, "Advanced": 2}
    goal_families = {
        "Strength": "build", "Muscle gain": "build", "Power": "build",
        "Endurance": "burn", "Weight loss": "burn", "Conditioning": "burn",
        "Flexibility": "recover", "Rehabilitation": "recover",
    }

    scores = []
    user_lvl_idx = level_order.get(user_level, 0)
    user_family = goal_families.get(user_goal, "")

    for _, row in pool_df.iterrows():
        score = 1  # baseline

        # Level scoring
        row_lvl_idx = level_order.get(row["Level"], 0)
        diff = abs(user_lvl_idx - row_lvl_idx)
        if diff == 0:
            score += 3
        elif diff == 1:
            score += 2

        # Goal scoring
        if row["Goal"].lower() == user_goal.lower():
            score += 3
        elif goal_families.get(row["Goal"], "") == user_family and user_family:
            score += 1

        # Muscle scoring
        if row["Muscle"].lower() == user_muscle.lower():
            score += 4

        scores.append(score)

    pool_df = pool_df.copy()
    pool_df["_score"] = scores

    # First: exact muscle matches
    exact = pool_df[pool_df["Muscle"].str.lower() == user_muscle.lower()]
    exact = exact.sort_values("_score", ascending=False).drop_duplicates(subset="Name", keep="first")

    if len(exact) >= n:
        return exact.head(n)

    # Fill remaining spots with related muscle groups (from dataset)
    remaining = n - len(exact)
    related = related_map.get(user_muscle, [])
    related_df = pool_df[pool_df["Muscle"].isin(related)]
    related_df = related_df.sort_values("_score", ascending=False).drop_duplicates(subset="Name", keep="first")
    # Exclude exercises already in exact matches
    related_df = related_df[~related_df["Name"].isin(exact["Name"])]

    result = pd.concat([exact, related_df.head(remaining)])
    return result


def get_duration(level):
    return {"Beginner": 30, "Intermediate": 45, "Advanced": 60}.get(level, 30)


# =============================================================================
# Load data + embeddings + muscle relationships
# =============================================================================
exercise_pool = load_exercise_pool()
embedding_model = load_embedding_model()
exercise_descriptions = build_exercise_descriptions(exercise_pool)
exercise_embeddings = compute_exercise_embeddings(embedding_model, exercise_descriptions)
muscle_relationships = load_muscle_relationships()


# =============================================================================
# Helper
# =============================================================================

def calculate_bmi(weight_kg, height_cm):
    height_m = height_cm / 100
    return round(weight_kg / (height_m ** 2), 1)


def bmi_category(bmi):
    if bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal weight"
    elif bmi < 30:
        return "Overweight"
    else:
        return "Obese"


def bmi_css_class(cat):
    return {
        "Underweight": "bmi-underweight",
        "Normal weight": "bmi-normal",
        "Overweight": "bmi-overweight",
        "Obese": "bmi-obese",
    }.get(cat, "")


def recommend_goal(bmi_cat):
    return {
        "Underweight": "Muscle gain",
        "Normal weight": "Strength",
        "Overweight": "Weight loss",
        "Obese": "Weight loss",
    }.get(bmi_cat, "Strength")


# --- From Data/Data.txt: WORKOUT_PARAMETERS ---
MUSCLE_GROUPS = ["Biceps", "Triceps", "Shoulders", "Chest", "Back", "Legs", "Abs"]
FITNESS_GOALS = [
    "Strength", "Endurance", "Muscle gain", "Weight loss",
    "Flexibility", "Power", "Conditioning", "Rehabilitation",
]
FITNESS_LEVELS = ["Beginner", "Intermediate", "Advanced"]


# =============================================================================
# APP LAYOUT
# =============================================================================

st.title("Your Personal Workout Planner")
st.markdown("Get a **personalised workout plan** based on your body and goals.")

st.divider()

# ---- TELL US ABOUT YOURSELF ----
st.header("Tell Us About Yourself")

input_col, result_col = st.columns(2)

user_name = input_col.text_input("Your name", "")

user_weight = input_col.slider("Weight (kg)", min_value=30, max_value=200, value=70, step=1)
user_height = input_col.slider("Height (cm)", min_value=120, max_value=220, value=170, step=1)

bmi = calculate_bmi(user_weight, user_height)
category = bmi_category(bmi)
css_class = bmi_css_class(category)
greeting = f"Hi {user_name}!" if user_name else "Hi there!"

result_col.markdown(
    f"""
    <div class="bmi-card {css_class}">
        <h3>{greeting}</h3>
        <h1>{bmi}</h1>
        <p style="font-size:1.2rem;"><strong>{category}</strong></p>
    </div>
    """,
    unsafe_allow_html=True,
)
result_col.write(f"**Weight:** {user_weight} kg")
result_col.write(f"**Height:** {user_height} cm")

rec_goal = recommend_goal(category)
result_col.info(f"Based on your BMI we suggest a focus on **{rec_goal}**.")

st.divider()

# ---- SEARCH FOR EXERCISES ----
st.header("Search for Exercises")
st.markdown("Type a **natural language query** to find exercises by meaning, not just keywords.")

search_query = st.text_input(
    "Describe the workout you're looking for",
    placeholder="e.g. easy chest workout for beginners, intense leg exercises, gentle stretching",
)

if search_query:
    search_results = semantic_search(
        search_query, exercise_pool, embedding_model, exercise_embeddings, muscle_relationships, n=5
    )

    st.subheader("Search Results")

    # Display results table with relevance score
    search_display = search_results[["Name", "Sets", "Reps", "Rest", "Difficulty", "Equipment"]].copy()
    search_display["Relevance"] = (search_results["_similarity"] * 100).round(1).astype(str) + "%"
    search_display.columns = ["Exercise", "Sets", "Reps", "Rest (sec)", "Difficulty", "Equipment", "Relevance"]
    search_display = search_display.reset_index(drop=True)

    st.dataframe(search_display, use_container_width=True, hide_index=True)

    # Show exercise images
    st.subheader("Exercise Guide — Correct Form")
    for _, row in search_results.iterrows():
        img_url = row["ImageURL"] if pd.notna(row["ImageURL"]) and row["ImageURL"] else None
        ref_url = row["RefURL"] if pd.notna(row["RefURL"]) and row["RefURL"] else None

        if img_url:
            col_img, col_info = st.columns([1, 1])
            col_img.image(img_url, use_container_width=True)
            col_info.markdown(f"### {row['Name']}")
            col_info.write(f"**Sets:** {row['Sets']}  |  **Reps:** {row['Reps']}  |  **Rest:** {row['Rest']}s")
            col_info.write(f"**Difficulty:** {row['Difficulty']}  |  **Equipment:** {row['Equipment']}")
            col_info.write(f"**Relevance:** {row['_similarity'] * 100:.1f}%")
            if ref_url:
                col_info.markdown(f"[View full exercise guide]({ref_url})")
            st.divider()
        else:
            st.markdown(f"### {row['Name']}")
            st.write(f"**Sets:** {row['Sets']}  |  **Reps:** {row['Reps']}  |  **Rest:** {row['Rest']}s")
            st.write(f"**Difficulty:** {row['Difficulty']}  |  **Equipment:** {row['Equipment']}")
            st.caption("Image not yet available for this exercise.")
            st.divider()

st.divider()

# ---- WORKOUT PREFERENCES ----
st.header("Workout Preferences")

pref1, pref2, pref3 = st.columns(3)

fitness_level = pref1.selectbox("What is your fitness level?", FITNESS_LEVELS, index=0)

fitness_goal = pref2.selectbox(
    "What is your fitness goal?",
    FITNESS_GOALS,
    index=FITNESS_GOALS.index(rec_goal) if rec_goal in FITNESS_GOALS else 0,
)

target_muscle = pref3.selectbox("Which muscle group do you want to target?", MUSCLE_GROUPS, index=0)

st.divider()

# ---- RECOMMENDED WORKOUT ----
st.header("Your Recommended Workout")

top_exercises = recommend_exercises(exercise_pool, fitness_level, fitness_goal, target_muscle, muscle_relationships)

duration = get_duration(fitness_level)

# Summary
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"**Duration**<br><span style='font-size:1.6rem;'>{duration} min</span>", unsafe_allow_html=True)
c2.markdown(f"**Level**<br><span style='font-size:1.6rem;'>{fitness_level}</span>", unsafe_allow_html=True)
c3.markdown(f"**Goal**<br><span style='font-size:1.6rem;'>{fitness_goal}</span>", unsafe_allow_html=True)
c4.markdown(f"**Target**<br><span style='font-size:1.6rem;'>{target_muscle}</span>", unsafe_allow_html=True)

st.write("")

# Build clean table for display
display_df = top_exercises[["Name", "Sets", "Reps", "Rest", "Difficulty", "Equipment"]].copy()
display_df.columns = ["Exercise", "Sets", "Reps", "Rest (sec)", "Difficulty", "Equipment"]
display_df = display_df.reset_index(drop=True)

st.dataframe(display_df, use_container_width=True, hide_index=True)

# Show exercise images with correct form
st.subheader("Exercise Guide — Correct Form")

exercise_names = display_df["Exercise"].tolist()
for ex_name in exercise_names:
    ex_pool_row = top_exercises[top_exercises["Name"] == ex_name].iloc[0]
    img_url = ex_pool_row["ImageURL"] if pd.notna(ex_pool_row["ImageURL"]) and ex_pool_row["ImageURL"] else None
    ref_url = ex_pool_row["RefURL"] if pd.notna(ex_pool_row["RefURL"]) and ex_pool_row["RefURL"] else None

    if img_url:
        col_img, col_info = st.columns([1, 1])
        col_img.image(img_url, use_container_width=True)
        # Get exercise details from the display table
        ex_row = display_df[display_df["Exercise"] == ex_name].iloc[0]
        col_info.markdown(f"### {ex_name}")
        col_info.write(f"**Sets:** {ex_row['Sets']}  |  **Reps:** {ex_row['Reps']}  |  **Rest:** {ex_row['Rest (sec)']}s")
        col_info.write(f"**Difficulty:** {ex_row['Difficulty']}  |  **Equipment:** {ex_row['Equipment']}")
        if ref_url:
            col_info.markdown(f"[View full exercise guide]({ref_url})")
        st.divider()
    else:
        st.markdown(f"### {ex_name}")
        ex_row = display_df[display_df["Exercise"] == ex_name].iloc[0]
        st.write(f"**Sets:** {ex_row['Sets']}  |  **Reps:** {ex_row['Reps']}  |  **Rest:** {ex_row['Rest (sec)']}s")
        st.write(f"**Difficulty:** {ex_row['Difficulty']}  |  **Equipment:** {ex_row['Equipment']}")
        st.caption("Image not yet available for this exercise.")
        st.divider()

# Show which dataset plans were used
st.caption(
    "Exercises sourced from: "
    + ", ".join(sorted(top_exercises["Source"].unique()))
)

