import streamlit as st
import pandas as pd

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
    """
    Build one DataFrame of every exercise in the dataset.
    Sources:
      - Data/Data.txt  : 3 sample workout plans (12 exercises)
      - RapidAPI.ipynb  : generateWorkoutPlan response (12 exercises)
      - RapidAPI.ipynb  : customWorkoutPlan response  (12 exercises)
    Each row is tagged with the context it came from so the recommender
    can score it against the user's profile.
    """
    rows = []

    # ---- Data/Data.txt: Beginner / Strength / Biceps ----
    for ex in [
        {"Name": "Dumbbell Curl",         "Sets": 3, "Reps": 12, "Rest": 60,  "Difficulty": "Easy",   "Equipment": "Dumbbells"},
        {"Name": "Incline Dumbbell Curl",  "Sets": 3, "Reps": 10, "Rest": 90,  "Difficulty": "Medium", "Equipment": "Dumbbells"},
        {"Name": "Hammer Curl",            "Sets": 3, "Reps": 12, "Rest": 60,  "Difficulty": "Easy",   "Equipment": "Dumbbells"},
    ]:
        rows.append({**ex, "Level": "Beginner", "Goal": "Strength", "Muscle": "Biceps", "Source": "Data.txt"})

    # ---- Data/Data.txt: Intermediate / Muscle gain / Chest ----
    for ex in [
        {"Name": "Barbell Bench Press",    "Sets": 4, "Reps": 8,  "Rest": 120, "Difficulty": "Hard",   "Equipment": "Barbell"},
        {"Name": "Incline Dumbbell Press",  "Sets": 4, "Reps": 10, "Rest": 90,  "Difficulty": "Medium", "Equipment": "Dumbbells"},
        {"Name": "Cable Flyes",             "Sets": 3, "Reps": 12, "Rest": 60,  "Difficulty": "Medium", "Equipment": "Cable machine"},
        {"Name": "Dips",                    "Sets": 3, "Reps": 10, "Rest": 90,  "Difficulty": "Medium", "Equipment": "Bodyweight"},
    ]:
        rows.append({**ex, "Level": "Intermediate", "Goal": "Muscle gain", "Muscle": "Chest", "Source": "Data.txt"})

    # ---- Data/Data.txt: Advanced / Endurance / Legs ----
    for ex in [
        {"Name": "Barbell Back Squat",     "Sets": 5, "Reps": 5,  "Rest": 180, "Difficulty": "Hard",   "Equipment": "Barbell"},
        {"Name": "Leg Press",               "Sets": 4, "Reps": 15, "Rest": 90,  "Difficulty": "Medium", "Equipment": "Cable machine"},
        {"Name": "Leg Curl",                "Sets": 4, "Reps": 12, "Rest": 60,  "Difficulty": "Medium", "Equipment": "Cable machine"},
        {"Name": "Leg Extension",           "Sets": 3, "Reps": 15, "Rest": 60,  "Difficulty": "Easy",   "Equipment": "Cable machine"},
        {"Name": "Calf Raises",             "Sets": 3, "Reps": 20, "Rest": 45,  "Difficulty": "Easy",   "Equipment": "Barbell"},
    ]:
        rows.append({**ex, "Level": "Advanced", "Goal": "Endurance", "Muscle": "Legs", "Source": "Data.txt"})

    # ---- RapidAPI.ipynb: generateWorkoutPlan (Build muscle, 4 days) ----
    api_build = {
        "Monday (Legs)": [
            {"Name": "Barbell Squats",    "Sets": 4, "Reps": 10, "Rest": 90, "Difficulty": "Hard",   "Equipment": "Barbell"},
            {"Name": "Leg Press",          "Sets": 3, "Reps": 12, "Rest": 75, "Difficulty": "Medium", "Equipment": "Leg Press Machine"},
            {"Name": "Walking Lunges",     "Sets": 3, "Reps": 10, "Rest": 60, "Difficulty": "Medium", "Equipment": "Bodyweight"},
        ],
        "Tuesday (Chest/Shoulders)": [
            {"Name": "Bench Press",              "Sets": 4, "Reps": 10, "Rest": 90,  "Difficulty": "Hard",   "Equipment": "Barbell"},
            {"Name": "Dumbbell Shoulder Press",   "Sets": 3, "Reps": 11, "Rest": 75,  "Difficulty": "Medium", "Equipment": "Dumbbells"},
            {"Name": "Push-Ups",                  "Sets": 3, "Reps": 17, "Rest": 45,  "Difficulty": "Easy",   "Equipment": "Bodyweight"},
        ],
        "Thursday (Back)": [
            {"Name": "Deadlift",                  "Sets": 4, "Reps": 9,  "Rest": 120, "Difficulty": "Hard",   "Equipment": "Barbell"},
            {"Name": "Bent-Over Rows",             "Sets": 3, "Reps": 11, "Rest": 75,  "Difficulty": "Medium", "Equipment": "Barbell"},
            {"Name": "Pull-Ups",                   "Sets": 3, "Reps": 10, "Rest": 90,  "Difficulty": "Hard",   "Equipment": "Bodyweight"},
        ],
        "Friday (Abs)": [
            {"Name": "Plank",              "Sets": 3, "Reps": 1,  "Rest": 30, "Difficulty": "Easy",   "Equipment": "Bodyweight"},
            {"Name": "Bicycle Crunches",   "Sets": 3, "Reps": 17, "Rest": 30, "Difficulty": "Medium", "Equipment": "Bodyweight"},
            {"Name": "Russian Twists",     "Sets": 3, "Reps": 20, "Rest": 30, "Difficulty": "Medium", "Equipment": "Medicine ball"},
        ],
    }
    muscle_map = {
        "Monday (Legs)": "Legs",
        "Tuesday (Chest/Shoulders)": "Chest",
        "Thursday (Back)": "Back",
        "Friday (Abs)": "Abs",
    }
    for day_label, exercises in api_build.items():
        muscle = muscle_map[day_label]
        for ex in exercises:
            rows.append({**ex, "Level": "Intermediate", "Goal": "Muscle gain", "Muscle": muscle, "Source": "API-BuildMuscle"})

    # ---- RapidAPI.ipynb: customWorkoutPlan (Overall fitness, yoga/HIIT) ----
    api_fitness = {
        "Monday": [
            {"Name": "Gentle Yoga Flow",   "Sets": 1, "Reps": 1,  "Rest": 0,  "Difficulty": "Easy",   "Equipment": "Bodyweight"},
            {"Name": "Plank (Modified)",    "Sets": 2, "Reps": 2,  "Rest": 30, "Difficulty": "Easy",   "Equipment": "Bodyweight"},
            {"Name": "Bird Dog",            "Sets": 2, "Reps": 12, "Rest": 30, "Difficulty": "Easy",   "Equipment": "Bodyweight"},
        ],
        "Tuesday": [
            {"Name": "HIIT Circuit (Low Impact)", "Sets": 1, "Reps": 1, "Rest": 0,  "Difficulty": "Medium", "Equipment": "Bodyweight"},
            {"Name": "Child's Pose Stretch",       "Sets": 1, "Reps": 1, "Rest": 0,  "Difficulty": "Easy",   "Equipment": "Bodyweight"},
        ],
        "Wednesday": [
            {"Name": "Yoga for Flexibility", "Sets": 1, "Reps": 1,  "Rest": 0,  "Difficulty": "Easy",   "Equipment": "Bodyweight"},
            {"Name": "Bridge Exercise",       "Sets": 3, "Reps": 15, "Rest": 45, "Difficulty": "Easy",   "Equipment": "Bodyweight"},
        ],
        "Thursday": [
            {"Name": "Low Impact HIIT",     "Sets": 1, "Reps": 1,  "Rest": 0,  "Difficulty": "Medium", "Equipment": "Bodyweight"},
            {"Name": "Cat-Cow Stretch",     "Sets": 1, "Reps": 1,  "Rest": 0,  "Difficulty": "Easy",   "Equipment": "Bodyweight"},
        ],
        "Friday": [
            {"Name": "Yoga for Core",       "Sets": 1, "Reps": 1,  "Rest": 0,  "Difficulty": "Easy",   "Equipment": "Bodyweight"},
            {"Name": "Side Planks",          "Sets": 2, "Reps": 2,  "Rest": 30, "Difficulty": "Medium", "Equipment": "Bodyweight"},
        ],
    }
    fitness_muscle_map = {
        "Monday": "Abs", "Tuesday": "Abs", "Wednesday": "Back",
        "Thursday": "Legs", "Friday": "Abs",
    }
    for day_label, exercises in api_fitness.items():
        muscle = fitness_muscle_map[day_label]
        for ex in exercises:
            rows.append({**ex, "Level": "Beginner", "Goal": "Weight loss", "Muscle": muscle, "Source": "API-Fitness"})

    return pd.DataFrame(rows)


# =============================================================================
# EXERCISE IMAGES — sourced from user-provided URLs
# =============================================================================

EXERCISE_IMAGES = {
    # Data.txt exercises
    "Dumbbell Curl":         "https://weighttraining.guide/wp-content/uploads/2016/05/Dumbbell-Alternate-Biceps-Curl-resized.png",
    "Incline Dumbbell Curl": "https://weighttraining.guide/wp-content/uploads/2017/01/Incline-Dumbbell-Curl-resized.png",
    "Hammer Curl":           "https://weighttraining.guide/wp-content/uploads/2016/11/Dumbbell-Hammer-Curl-resized.png",
    "Barbell Bench Press":   "https://weighttraining.guide/wp-content/uploads/2016/05/Barbell-Bench-Press-resized.png",
    "Incline Dumbbell Press":"https://weighttraining.guide/wp-content/uploads/2016/11/incline-dumbbell-bench-press-resized.png",
    "Cable Flyes":           "https://weighttraining.guide/wp-content/uploads/2016/05/cable-cross-over-resized.png",
    "Dips":                  "https://training.fit/wp-content/uploads/2020/03/arnold-dips-800x448.png",
    "Barbell Back Squat":    "https://weighttraining.guide/wp-content/uploads/2016/10/barbell-squat-resized-FIXED-2.png",
    "Leg Press":             "https://training.fit/wp-content/uploads/2020/03/beinpresse-800x448.png",
    "Leg Curl":              "https://training.fit/wp-content/uploads/2020/03/beinbeugen-liegend-geraet.png",
    "Leg Extension":         "https://weighttraining.guide/wp-content/uploads/2016/05/lever-leg-extension-resized.png",
    "Calf Raises":           "https://cdn.athlemove.com/bbdba77e-b34b-4683-bdcb-ffce756d42b8.webp",
    # API-BuildMuscle exercises
    "Barbell Squats":        "https://weighttraining.guide/wp-content/uploads/2016/10/barbell-squat-resized-FIXED-2.png",
    "Walking Lunges":        "https://substackcdn.com/image/fetch/f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fff9ba04b-3ea8-4a50-94d0-a30493b96310_1392x590.jpeg",
    "Bench Press":           "https://training.fit/wp-content/uploads/2018/11/bankdruecken-flachbank-langhantel-800x448.png",
    "Dumbbell Shoulder Press":"https://training.fit/wp-content/uploads/2020/03/schulterdruecken-kurzhanteln-800x448.png",
    "Push-Ups":              "https://training.fit/wp-content/uploads/2020/02/liegestuetze-800x448.png",
    "Deadlift":              "https://weighttraining.guide/wp-content/uploads/2016/05/Barbell-Deadlift-1.png",
    "Bent-Over Rows":        "https://weighttraining.guide/wp-content/uploads/2016/10/Bent-over-barbell-row.png",
    "Pull-Ups":              "https://weighttraining.guide/wp-content/uploads/2016/10/pull-up-2-resized.png",
    "Plank":                 "https://fitnessprogramer.com/wp-content/uploads/2021/02/plank.gif",
    "Bicycle Crunches":      "https://weighttraining.guide/wp-content/uploads/2016/11/bicycle-crunch-resized-1.png",
    "Russian Twists":        "https://www.anterides.com/UserFiles/images/exercises/square-annotated/2-Russian-Twist-WEB-F.png",
    # API-Fitness exercises
    "Gentle Yoga Flow":      "https://cdn.prod.website-files.com/683b218dcc58f93d54ce8e1d/686c0c2dc33d11fb8faac7f2_686b758ae328c53c41195a91_slow%2520flow%2520yoga.webp",
    "Plank (Modified)":      "https://fitnessprogramer.com/wp-content/uploads/2021/02/plank.gif",
    "Bird Dog":              "https://spotebi.com/wp-content/uploads/2014/10/bird-dogs-exercise-illustration.jpg",
    "Bridge Exercise":       "https://spotebi.com/wp-content/uploads/2015/01/glute-bridge-exercise-illustration.jpg",
    "Side Planks":           "https://weighttraining.guide/wp-content/uploads/2023/03/High-one-leg-side-plank.png",
}

# Reference pages for each exercise (from user-provided links)
EXERCISE_REFS = {
    "Dumbbell Curl":         "https://fitnessvolt.com/dumbbell-curl-biceps/",
    "Incline Dumbbell Curl": "https://weighttraining.guide/exercises/incline-dumbbell-curl/",
    "Hammer Curl":           "https://weighttraining.guide/exercises/dumbbell-hammer-curl/",
    "Barbell Bench Press":   "https://weighttraining.guide/exercises/bench-press/",
    "Incline Dumbbell Press":"https://weighttraining.guide/exercises/incline-dumbbell-bench-press/",
    "Cable Flyes":           "https://weighttraining.guide/exercises/cable-cross-over/",
    "Dips":                  "https://training.fit/exercise/bench-dip/",
    "Barbell Back Squat":    "https://weighttraining.guide/exercises/barbell-squat/",
    "Leg Press":             "https://training.fit/exercise/seated-leg-press/",
    "Leg Curl":              "https://training.fit/exercise/lying-leg-curl/",
    "Leg Extension":         "https://fitnessvolt.com/leg-extension/",
    "Calf Raises":           "https://athlemove.com/exercises/dumbbell-standing-calf-raise",
    "Barbell Squats":        "https://fitnessvolt.com/24669/barbell-squat/",
    "Walking Lunges":        "https://solanabroker.substack.com/p/what-are-lunges-and-why-are-they",
    "Bench Press":           "https://training.fit/exercise/benchpress/",
    "Dumbbell Shoulder Press":"https://training.fit/exercise/dumbbell-shoulder-press/",
    "Push-Ups":              "https://training.fit/exercise/push-ups/",
    "Deadlift":              "https://weighttraining.guide/exercises/barbell-deadlift/",
    "Bent-Over Rows":        "https://fitnessvolt.com/31615/bent-over-rows-guide/",
    "Pull-Ups":              "https://weighttraining.guide/exercises/pull-up/",
    "Plank":                 "https://fitnessprogramer.com/exercise/plank/",
    "Bicycle Crunches":      "https://weighttraining.guide/exercises/bicycle-crunch/",
    "Russian Twists":        "https://www.anterides.com/exercise/159/russian-twist",
    "Gentle Yoga Flow":      "https://myyogateacher.com/articles/slow-flow-yoga-sequence",
    "Bird Dog":              "https://spotebi.com/exercise-guide/bird-dogs/",
    "Bridge Exercise":       "https://spotebi.com/exercise-guide/glute-bridge/",
    "Side Planks":           "https://weighttraining.guide/exercises/high-one-leg-side-plank/",
}


# =============================================================================
# RECOMMENDATION ENGINE — scores every dataset exercise for the user
# =============================================================================

def recommend_exercises(pool_df, user_level, user_goal, user_muscle, n=5):
    """
    Score each exercise in the dataset pool and return the top-n.

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

    # Sort by score descending, then drop duplicates (same exercise name)
    result = (
        pool_df
        .sort_values("_score", ascending=False)
        .drop_duplicates(subset="Name", keep="first")
        .head(n)
    )

    return result


def get_duration(level):
    return {"Beginner": 30, "Intermediate": 45, "Advanced": 60}.get(level, 30)


# =============================================================================
# Load data
# =============================================================================
exercise_pool = load_exercise_pool()


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
MUSCLE_GROUPS = ["Biceps", "Chest", "Back", "Legs", "Abs"]
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

# ---- STEP 1 ----
st.header("Step 1 — Tell us about yourself")

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

# ---- STEP 2 ----
st.header("Step 2 — Choose your workout preferences")

pref1, pref2, pref3 = st.columns(3)

fitness_level = pref1.selectbox("What is your fitness level?", FITNESS_LEVELS, index=0)

fitness_goal = pref2.selectbox(
    "What is your fitness goal?",
    FITNESS_GOALS,
    index=FITNESS_GOALS.index(rec_goal) if rec_goal in FITNESS_GOALS else 0,
)

target_muscle = pref3.selectbox("Which muscle group do you want to target?", MUSCLE_GROUPS, index=0)

st.divider()

# ---- STEP 3 ----
st.header("Step 3 — Your Recommended Workout")

top_exercises = recommend_exercises(exercise_pool, fitness_level, fitness_goal, target_muscle)

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
    img_url = EXERCISE_IMAGES.get(ex_name)
    ref_url = EXERCISE_REFS.get(ex_name)

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
