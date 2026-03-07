import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from exercise_instructions import exercise_instructions

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


@st.cache_data
def load_exercise_muscle_map():
    """
    Build a mapping of exercise name -> all muscle groups it trains,
    from workout_creator_dataset.json.
    e.g. {"Barbell Bench Press": ["Chest", "Triceps", "Shoulders"], ...}
    """
    json_path = Path(__file__).parent / "Data" / "workout_creator_dataset.json"
    with open(json_path) as f:
        data = json.load(f)

    return {ex["name"]: ex["muscleGroups"] for ex in data["exercises"]}


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


@st.cache_data
def compute_limitation_embeddings(_model, descriptions):
    """Compute embeddings for physical limitation descriptions (cached)."""
    return _model.encode(list(descriptions))


def match_limitations(user_text, model, limit_keys, limit_embeddings, threshold=0.30):
    """Semantically match user-typed text to limitation categories."""
    if not user_text.strip():
        return []
    user_emb = model.encode([user_text])
    sims = cosine_similarity(user_emb, limit_embeddings)[0]
    return [limit_keys[i] for i, s in enumerate(sims) if s >= threshold]


def semantic_search(query, pool_df, model, embeddings, ex_muscle_map, n=5):
    """Return top-n exercises most similar to the user's natural language query.
    Uses exercise-muscle map from workout_creator_dataset.json to find exercises
    that train the searched muscle group (primary or secondary)."""
    query_embedding = model.encode([query])
    similarities = cosine_similarity(query_embedding, embeddings)[0]
    pool_df = pool_df.copy()
    pool_df["_similarity"] = similarities

    # Build keyword mapping dynamically from all muscle group names
    # in both the exercise pool and the dataset JSON
    all_muscles = set(pool_df["Muscle"].unique())
    for muscles in ex_muscle_map.values():
        all_muscles.update(muscles)

    # Detect muscle group in query by checking if any muscle name
    # appears in the query (case-insensitive, partial match)
    query_lower = query.lower()
    detected_muscle = None
    for muscle in sorted(all_muscles, key=len, reverse=True):
        # Check for the muscle name or its singular form (e.g. "bicep" matches "Biceps")
        muscle_lower = muscle.lower()
        singular = muscle_lower.rstrip("s")
        if muscle_lower in query_lower or singular in query_lower:
            detected_muscle = muscle
            break

    if detected_muscle:
        # Find exercises that train this muscle:
        # 1. Primary muscle column matches
        # 2. OR the exercise trains this muscle according to the dataset JSON
        exercises_training_muscle = {
            name for name, muscles in ex_muscle_map.items()
            if detected_muscle in muscles
        }
        filtered = pool_df[
            (pool_df["Muscle"] == detected_muscle) |
            (pool_df["Name"].isin(exercises_training_muscle))
        ]
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
exercise_muscle_map = load_exercise_muscle_map()


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
    "Flexibility", "Power",
]
FITNESS_LEVELS = ["Beginner", "Intermediate", "Advanced"]

# Rich descriptions used for semantic matching of user-typed limitations
LIMITATION_DESCRIPTIONS = {
    "Pregnant / Postpartum": "pregnant, postpartum, after giving birth, expecting a baby, maternity, recently had a baby, new mother",
    "Bad knees": "bad knees, knee pain, knee injury, knee problems, sore knees, arthritic knees, knee surgery",
    "Bad back": "bad back, back pain, lower back pain, back injury, spine problems, herniated disc, sciatica, lumbar pain",
    "Shoulder injury": "shoulder injury, shoulder pain, rotator cuff, shoulder problems, sore shoulder, impingement, shoulder surgery",
}

# Safety blocklist: exercises to exclude per physical limitation
EXERCISE_BLOCKLIST = {
    "Pregnant / Postpartum": [
        "Deadlift", "Barbell Back Squat", "Barbell Squats", "Barbell Squat",
        "Hack Squat", "Smith Machine Squat", "HIIT Circuit (High Impact)",
        "Decline Sit-Ups", "Russian Twists", "Bicycle Crunches",
        "Leg Press", "Bench Press", "Barbell Bench Press",
    ],
    "Bad knees": [
        "Barbell Squats", "Barbell Back Squat", "Barbell Squat", "Dumbbell Squat",
        "Hack Squat", "Smith Machine Squat", "Walking Lunges",
        "Leg Extension", "HIIT Circuit (High Impact)", "Low Impact HIIT",
    ],
    "Bad back": [
        "Deadlift", "Barbell Bent-Over Row", "Dumbbell Bent-Over Row",
        "Bent-Over Rows", "Barbell Back Squat", "Barbell Squats",
        "Hack Squat", "Decline Sit-Ups", "Russian Twists",
        "Smith Machine Squat",
    ],
    "Shoulder injury": [
        "Barbell Shoulder Press", "Dumbbell Shoulder Press", "Machine Shoulder Press",
        "Lateral Raise", "Side Lateral Raises", "Overhead Tricep Extension",
        "Pull-Ups", "Dips", "Tricep Dips", "Upright Row",
        "Barbell Bench Press", "Bench Press", "Incline Dumbbell Press",
    ],
}

limitation_keys = list(LIMITATION_DESCRIPTIONS.keys())
limitation_embeddings = compute_limitation_embeddings(embedding_model, tuple(LIMITATION_DESCRIPTIONS.values()))


# =============================================================================
# APP LAYOUT
# =============================================================================

if "show_recommendations" not in st.session_state:
    st.session_state.show_recommendations = False

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

# ---- WORKOUT PREFERENCES (filters applied before search) ----
st.header("Workout Preferences")

pref1, pref2, pref3 = st.columns(3)

fitness_level = pref1.selectbox("What is your fitness level?", FITNESS_LEVELS, index=0)

fitness_goal = pref2.selectbox(
    "What is your fitness goal?",
    FITNESS_GOALS,
    index=FITNESS_GOALS.index(rec_goal) if rec_goal in FITNESS_GOALS else 0,
)

target_muscle = pref3.selectbox("Which muscle group do you want to target?", MUSCLE_GROUPS, index=0)

# Equipment filter
all_equipment = sorted(exercise_pool["Equipment"].dropna().unique().tolist())
selected_equipment = st.multiselect(
    "What equipment do you have available?",
    options=all_equipment,
    default=all_equipment,
)

# Physical limitations — semantic search
limitation_text = st.text_input(
    "Do you have any physical limitations or injuries?",
    placeholder="e.g. I have bad knees, I'm pregnant, lower back pain, shoulder injury...",
)
limitations = match_limitations(limitation_text, embedding_model, limitation_keys, limitation_embeddings)
if limitations:
    st.info(f"Detected: {', '.join(limitations)}")

# Workout duration
workout_minutes = st.slider("How much time do you have? (minutes)", min_value=15, max_value=90, value=45, step=5)

# Apply filters to exercise pool
blocked_exercises = set()
for limitation in limitations:
    blocked_exercises.update(EXERCISE_BLOCKLIST.get(limitation, []))

filtered_pool = exercise_pool.copy()
if selected_equipment:
    filtered_pool = filtered_pool[filtered_pool["Equipment"].isin(selected_equipment)]
if blocked_exercises:
    filtered_pool = filtered_pool[~filtered_pool["Name"].isin(blocked_exercises)]

# Calculate max exercises from available time (~4 min per exercise: 3 sets × 40s + 3 × 60s rest)
max_exercises = max(1, workout_minutes // 4)

if st.button("Find Exercises", type="primary", use_container_width=True):
    st.session_state.show_recommendations = True

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
        search_query, filtered_pool, embedding_model, exercise_embeddings, exercise_muscle_map, n=5
    )

    st.subheader("Search Results")

    # Display results table with relevance score
    search_display = search_results[["Name", "Sets", "Reps", "Rest", "Difficulty", "Equipment"]].copy()
    search_display.columns = ["Exercise", "Sets", "Reps", "Rest (sec)", "Difficulty", "Equipment"]
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
            if ref_url:
                col_info.markdown(f"[View full exercise guide]({ref_url})")

            # Display instructions
            instructions = exercise_instructions.get(row['Name'], "Instructions not available for this exercise.")
            st.markdown("**How to Perform:**")
            st.write(instructions)
            st.divider()
        else:
            st.markdown(f"### {row['Name']}")
            st.write(f"**Sets:** {row['Sets']}  |  **Reps:** {row['Reps']}  |  **Rest:** {row['Rest']}s")
            st.write(f"**Difficulty:** {row['Difficulty']}  |  **Equipment:** {row['Equipment']}")
            st.caption("Image not yet available for this exercise.")

            # Display instructions
            instructions = exercise_instructions.get(row['Name'], "Instructions not available for this exercise.")
            st.markdown("**How to Perform:**")
            st.write(instructions)
            st.divider()

# ---- RECOMMENDED WORKOUT ----
if st.session_state.show_recommendations:
    st.header("Your Recommended Workout")

    top_exercises = recommend_exercises(filtered_pool, fitness_level, fitness_goal, target_muscle, muscle_relationships, n=max_exercises)

    # Summary
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Duration**<br><span style='font-size:1.6rem;'>{workout_minutes} min</span>", unsafe_allow_html=True)
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
            ex_row = display_df[display_df["Exercise"] == ex_name].iloc[0]
            col_info.markdown(f"### {ex_name}")
            col_info.write(f"**Sets:** {ex_row['Sets']}  |  **Reps:** {ex_row['Reps']}  |  **Rest:** {ex_row['Rest (sec)']}s")
            col_info.write(f"**Difficulty:** {ex_row['Difficulty']}  |  **Equipment:** {ex_row['Equipment']}")
            if ref_url:
                col_info.markdown(f"[View full exercise guide]({ref_url})")

            instructions = exercise_instructions.get(ex_name, "Instructions not available for this exercise.")
            st.markdown("**How to Perform:**")
            st.write(instructions)
            st.divider()
        else:
            st.markdown(f"### {ex_name}")
            ex_row = display_df[display_df["Exercise"] == ex_name].iloc[0]
            st.write(f"**Sets:** {ex_row['Sets']}  |  **Reps:** {ex_row['Reps']}  |  **Rest:** {ex_row['Rest (sec)']}s")
            st.write(f"**Difficulty:** {ex_row['Difficulty']}  |  **Equipment:** {ex_row['Equipment']}")
            st.caption("Image not yet available for this exercise.")

            instructions = exercise_instructions.get(ex_name, "Instructions not available for this exercise.")
            st.markdown("**How to Perform:**")
            st.write(instructions)
            st.divider()

    st.caption(
        "Exercises sourced from: "
        + ", ".join(sorted(top_exercises["Source"].unique()))
    )

