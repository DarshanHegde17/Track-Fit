from flask import Flask, render_template, request, redirect
from pymongo import MongoClient
from datetime import date, datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import openai
import json

app = Flask(__name__)

# -----------------------------
# OpenAI API Key (OPTIONAL)
# -----------------------------
openai.api_key = "YOUR_OPENAI_API_KEY"

# -----------------------------
# MongoDB Connection
# -----------------------------
client = MongoClient("mongodb://localhost:27017/")
db = client["fitness_app"]

# -----------------------------
# Collections
# -----------------------------
meals_collection = db["meals"]
workouts_collection = db["workouts"]
steps_collection = db["steps"]
water_collection = db["water"]
calories_collection = db["daily_calories"]
nutrition_collection = db["nutrition_items"]
plans_collection = db["nutrition_plans"]
tips_collection = db["nutrition_tips"]


today = str(date.today())
meal = meals_collection.find_one({"date": today})



# -----------------------------
# DASHBOARD
# -----------------------------
@app.route("/")
def dashboard():
    cards = [
        {"icon": "🍽️", "title": "Daily Meal", "description": "View today’s meal plan", "link": "/meal"},
        {"icon": "🏃‍♂️", "title": "Steps", "description": "Track your daily steps", "link": "/steps"},
        {"icon": "💧", "title": "Water", "description": "Hydration monitoring", "link": "#"},
        {"icon": "🧘‍♂️", "title": "Yoga", "description": "Mind & body balance", "link": "#"},
        {"icon": "🏋️", "title": "Workout", "description": "Strength training plans", "link": "/workout"},
        {"icon": "📅", "title": "Monthly Progress", "description": "View monthly fitness report", "link": "/monthly-progress"},

        {"icon": "🥗", "title": "Nutrition", "description": "Healthy food plans", "link": "/meal/search"},
        {"icon": "📊", "title": "Progress", "description": "View reports", "link": "/today-progress"},

        {"icon": "⚙️", "title": "Settings", "description": "Customize dashboard", "link": "#"},
    ]
    return render_template("dashboard.html", cards=cards)

# -----------------------------
# TODAY'S MEAL
# -----------------------------
@app.route("/meal")
def today_meal():
    today = str(date.today())
    meal = meals_collection.find_one({"date": today})

    # If no meal exists yet, create empty template
    if not meal:
        meal = {
            "date": today,
            "breakfast": {"name": "", "calories": 0, "protein": 0, "carbs": 0, "fats": 0},
            "lunch": {"name": "", "calories": 0, "protein": 0, "carbs": 0, "fats": 0},
            "dinner": {"name": "", "calories": 0, "protein": 0, "carbs": 0, "fats": 0}
        }
        meals_collection.insert_one(meal)

    return render_template("meal.html", meal=meal, today=today)



# -----------------------------
# SAVE MEAL
# -----------------------------
@app.route("/meal/save", methods=["POST"])
def save_meal():
    today = str(date.today())

    meal_data = {
        "date": today,
        "breakfast": {
            "name": request.form.get("b_name", ""),
            "calories": int(request.form.get("b_cal", 0) or 0),
            "protein": int(request.form.get("b_pro", 0) or 0),
            "carbs": int(request.form.get("b_carbs", 0) or 0),
            "fats": int(request.form.get("b_fats", 0) or 0),
        },
        "lunch": {
            "name": request.form.get("l_name", ""),
            "calories": int(request.form.get("l_cal", 0) or 0),
            "protein": int(request.form.get("l_pro", 0) or 0),
            "carbs": int(request.form.get("l_carbs", 0) or 0),
            "fats": int(request.form.get("l_fats", 0) or 0),
        },
        "dinner": {
            "name": request.form.get("d_name", ""),
            "calories": int(request.form.get("d_cal", 0) or 0),
            "protein": int(request.form.get("d_pro", 0) or 0),
            "carbs": int(request.form.get("d_carbs", 0) or 0),
            "fats": int(request.form.get("d_fats", 0) or 0),
        }
    }

    meals_collection.update_one(
        {"date": today},
        {"$set": meal_data},
        upsert=True
    )

    return redirect("/meal")


 
 

# -----------------------------
# CLEAR TODAY'S MEAL (MIDNIGHT)\


# -----------------------------
def clear_today_meal():
    today = str(date.today())
    meals_collection.delete_many({"date": today})
    print("Today's meal cleared at midnight")



    

# -----------------------------
# GPT NUTRITION SEARCH
# -----------------------------
def get_nutrition_from_gpt(meal_name):
    try:
        prompt = f"Give nutrition facts for {meal_name} as JSON: calories, protein, fat, fiber"

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        return json.loads(response["choices"][0]["message"]["content"])
    except Exception as e:
        print("GPT ERROR:", e)
        return None

# -----------------------------
# MEAL SEARCH
# -----------------------------
@app.route("/meal/search", methods=["GET", "POST"])
def meal_search():
    result = None
    meal_name = ""
    searched = False

    if request.method == "POST":
        meal_name = request.form.get("meal_name", "").strip()
        searched = True

        nutrition_data = {
            "Apple": {"calories": 52, "protein": 0.3, "fat": 0.2, "fiber": 2.4},
            "Banana": {"calories": 89, "protein": 1.1, "fat": 0.3, "fiber": 2.6},
        }

        data = nutrition_data.get(meal_name.title()) or get_nutrition_from_gpt(meal_name)

        if data:
            result = {"name": meal_name.title(), **data}
        else:
            return redirect(f"https://www.google.com/search?q={meal_name}+nutrition+facts")

    return render_template(
        "meal_search.html",
        result=result,
        meal_name=meal_name,
        searched=searched
    )

# -----------------------------
# STEPS TRACKING
# -----------------------------
@app.route("/steps", methods=["GET", "POST"])
def steps():
    today = str(date.today())
    user = "default_user"

    step_data = steps_collection.find_one({"date": today, "user": user})
    if not step_data:
        step_data = {"total_steps": 0, "total_km": 0, "total_calories": 0}

    if request.method == "POST":
        new_steps = int(request.form.get("steps", 0))
        distance = new_steps * 0.0008
        calories = new_steps * 0.04

        total_steps = step_data["total_steps"] + new_steps
        total_km = step_data["total_km"] + distance
        total_calories = step_data["total_calories"] + calories

        steps_collection.update_one(
            {"date": today, "user": user},
            {"$set": {
                "total_steps": total_steps,
                "total_km": total_km,
                "total_calories": total_calories
            }},
            upsert=True
        )

        step_data = {
            "total_steps": total_steps,
            "total_km": total_km,
            "total_calories": total_calories
        }

    return render_template("steps.html", step_data=step_data)

# -----------------------------
# CLEAR TODAY'S STEPS (MIDNIGHT)
# -----------------------------
def clear_today_steps():
    today = str(date.today())
    steps_collection.delete_many({"date": today})
    print("Today's steps cleared at midnight")

# -----------------------------
# WORKOUT
# -----------------------------
@app.route("/workout")
def daily_workout():
    workout_plan = [
        {
            "name": "Jumping Jacks",
            "calories": 25,
            "image": "images/jump.avif"
        },
        {
            "name": "Push Ups",
            "calories": 30,
            "image": "images/push.jpg"
        },
        {
            "name": "Squats",
            "calories": 28,
            "image": "images/sq.webp"
        },
        {
            "name": "Plank",
            "calories": 20,
            "image": "images/Plank.jpg"
        },
        {
            "name": "Mountain Climbers",
            "calories": 30,
            "image": "images/mount.webp"
        },
        {
            "name": "High Knees",
            "calories": 35,
            "image": "images/highknee.jpg"
        },
        {
            "name": "Burpees",
            "calories": 40,
            "image": "images/Burpees.avif"
        },
        {
            "name": "Lunges",
            "calories": 25,
            "image": "images/Lunges.avif"
        },
        {
            "name": "Wall Sit",
            "calories": 18,
            "image": "images/Wall Sit.avif"
        },
        {
            "name": "Crunches",
            "calories": 22,
            "image": "images/Crunches.jpg"
        },
        {
            "name": "Leg Raises",
            "calories": 20,
            "image": "images/Leg Raises.webp"
        },
        {
            "name": "Russian Twist",
            "calories": 24,
            "image": "images/Russian Twist.jpg"
        },
        {
            "name": "Bicycle Crunch",
            "calories": 26,
            "image": "images/Bicycle Crunch.jpg"
        },
        {
            "name": "Jump Squats",
            "calories": 32,
            "image": "images/Jump Squats.avif"
        },
        {
            "name": "Skater Jumps",
            "calories": 30,
            "image": "images/Skater Jumps.jpg"
        },
        {
            "name": "Butt Kicks",
            "calories": 28,
            "image": "images/Butt Kicks.jpg"
        },
        {
            "name": "Arm Circles",
            "calories": 15,
            "image": "images/Arm Circles.jpg"
        },
        {
            "name": "Tricep Dips",
            "calories": 25,
            "image": "images/Tricep Dips.jpg"
        },
        {
            "name": "Side Plank",
            "calories": 18,
            "image": "images/Side Plank.avif"
        },
        {
            "name": "Skipping (No Rope)",
            "calories": 35,
            "image": "images/Skipping.jpg"
        },
    ]

    return render_template("workout.html", workout_plan=workout_plan)



@app.route("/workout/save", methods=["POST"])
def save_workout():
    data = request.json

    workouts_collection.insert_one({
        "date": str(date.today()),
        "exercise": data["exercise"],
        "calories": data["calories"],
        "duration": 30,
        "time": datetime.now(),
        "completed": True
    })

    return {"status": "ok"}

# -----------------------------
# CLEAR TODAY'S WORKOUTS
# -----------------------------
def clear_today_workouts():
    workouts_collection.delete_many({"date": str(date.today())})
    print("Today's workouts cleared at midnight")

# -----------------------------
# SCHEDULER (MIDNIGHT RESET)
# -----------------------------
scheduler = BackgroundScheduler()

scheduler.add_job(clear_today_steps, "cron", hour=0, minute=0)
scheduler.add_job(clear_today_meal, "cron", hour=0, minute=0)
scheduler.add_job(clear_today_workouts, "cron", hour=0, minute=0)

scheduler.start()


@app.route("/water", methods=["GET", "POST"])
def water():
    today = str(date.today())
    user = "default_user"

    water_data = water_collection.find_one({"date": today, "user": user})
    if not water_data:
        water_data = {
            "goal": 8,          # default 8 glasses
            "current": 0
        }

    if request.method == "POST":

        # SET GOAL
        if "set_goal" in request.form:
            goal = int(request.form.get("goal"))
            water_collection.update_one(
                {"date": today, "user": user},
                {"$set": {"goal": goal, "current": 0}},
                upsert=True
            )
            return redirect("/water")

        # ADD ONE GLASS
        if "add_water" in request.form:
            if water_data["current"] < water_data["goal"]:
                water_data["current"] += 1

            water_collection.update_one(
                {"date": today, "user": user},
                {"$set": water_data},
                upsert=True
            )
            return redirect("/water")

    progress = int((water_data["current"] / water_data["goal"]) * 100) if water_data["goal"] else 0

    return render_template(
        "water.html",
        water=water_data,
        progress=progress
    )

def clear_today_water():
    water_collection.delete_many({"date": str(date.today())})
    print("Today's water intake reset")


    # -----------------------------
# DAILY CALORIES
# -----------------------------
@app.route("/daily-calories", methods=["GET", "POST"])
def daily_calories():
    today = str(date.today())
    user = "default_user"

    # --- Fetch stored manual additions from daily_calories ---
    data = calories_collection.find_one({"date": today, "user": user})
    if not data:
        data = {
            "date": today,
            "user": user,
            "goal": 2000,
            "manual_consumed": 0,  # only manual additions
            "manual_burned": 0
        }

    # --- Handle manual POST inputs ---
    if request.method == "POST":
        # Set new goal
        if "set_goal" in request.form:
            data["goal"] = int(request.form.get("goal"))
            # Optional: reset manual additions
            data["manual_consumed"] = 0
            data["manual_burned"] = 0

        # Add food calories manually
        if "add_food" in request.form:
            food_cal = int(request.form.get("food_cal"))
            data["manual_consumed"] += food_cal

        # Add burned calories manually
        if "add_exercise" in request.form:
            burn_cal = int(request.form.get("burn_cal"))
            data["manual_burned"] += burn_cal

    # --- Automatic calculation from meals ---
    consumed_auto = 0
    meal_doc = meals_collection.find_one({"date": today})
    if meal_doc:
        for meal in ["breakfast", "lunch", "dinner"]:
            if meal in meal_doc and meal_doc[meal].get("calories"):
                consumed_auto += int(meal_doc[meal]["calories"])

    # --- Automatic burned calories from workouts and steps ---
    burned_auto = 0
    workout_docs = workouts_collection.find({"date": today, "user": user})
    for w in workout_docs:
        burned_auto += w.get("calories", 0)

    step_doc = steps_collection.find_one({"date": today, "user": user})
    if step_doc:
        burned_auto += step_doc.get("total_calories", 0)

    # --- Combine automatic + manual values ---
    data["consumed"] = consumed_auto + data.get("manual_consumed", 0)
    data["burned"] = burned_auto + data.get("manual_burned", 0)

    remaining = data["goal"] - data["consumed"] + data["burned"]

    # --- Save updated daily calories ---
    calories_collection.update_one(
        {"date": today, "user": user},
        {"$set": data},
        upsert=True
    )

    return render_template(
        "daily_calories.html",
        data=data,
        remaining=remaining
    )


@app.route("/monthly-progress")
def monthly_progress():
    user = "default_user"
    today_date = date.today()
    start_date = today_date - timedelta(days=30)

    labels = []
    consumed_list = []
    burned_list = []
    water_list = []

    current = start_date
    while current <= today_date:
        d = str(current)
        labels.append(d[8:])  # show only day number

        # ---------------- Consumed Calories ----------------
        consumed = 0
        meal = meals_collection.find_one({"date": d})
        if meal:
            for m in ["breakfast", "lunch", "dinner"]:
                consumed += meal.get(m, {}).get("calories", 0)

        daily_cal = calories_collection.find_one({"date": d, "user": user})
        if daily_cal:
            consumed += daily_cal.get("manual_consumed", 0)

        # ---------------- Burned Calories ----------------
        burned = 0

        steps = steps_collection.find_one({"date": d, "user": user})
        if steps:
            burned += steps.get("total_calories", 0)

        workouts = workouts_collection.find({"date": d})
        for w in workouts:
            burned += w.get("calories", 0)

        if daily_cal:
            burned += daily_cal.get("manual_burned", 0)

        # ---------------- Water Intake ----------------
        water = water_collection.find_one({"date": d, "user": user})
        water_list.append(water.get("current", 0) if water else 0)

        consumed_list.append(consumed)
        burned_list.append(burned)

        current += timedelta(days=1)

    return render_template(
        "monthly_progress.html",
        labels=labels,
        consumed=consumed_list,
        burned=burned_list,
        water=water_list
    )

@app.route("/nutrition")
def nutrition():
    veg = list(nutrition_collection.find({"type": "veg"}))
    nonveg = list(nutrition_collection.find({"type": "nonveg"}))
    keto = list(nutrition_collection.find({"category": "keto"}))
    lowcarb = list(nutrition_collection.find({"category": "lowcarb"}))
    highfat = list(nutrition_collection.find({"category": "highfat"}))

    plans = list(plans_collection.find())
    tips = list(tips_collection.find())

    return render_template(
        "nutrition.html",
        veg=veg,
        nonveg=nonveg,
        keto=keto,
        lowcarb=lowcarb,
        highfat=highfat,
        plans=plans,
        tips=tips
    )

@app.route("/today-progress", methods=["GET"])
def today_progress():
    today = str(date.today())
    user = "default_user"

    # -------- READ FINAL DAILY CALORIES (SOURCE OF TRUTH) --------
    daily = calories_collection.find_one({"date": today, "user": user})

    if not daily:
        daily = {
            "goal": 2000,
            "consumed": 0,
            "burned": 0
        }

    goal = daily.get("goal", 2000)
    consumed = daily.get("consumed", 0)
    burned = daily.get("burned", 0)
    remaining = max(0, goal - consumed + burned)

    # -------- WATER --------
    water = water_collection.find_one({"date": today, "user": user})
    water_current = water.get("current", 0) if water else 0
    water_goal = water.get("goal", 8) if water else 8

    data = {
        "goal": goal,
        "consumed": consumed,
        "burned": burned,
        "remaining": remaining,
        "water_current": water_current,
        "water_goal": water_goal
    }

    return render_template("today_progress.html", data=data)

  
# -----------------------------
# ABOUT PAGE
# -----------------------------
@app.route("/about")
def about():
    return render_template("about.html")



@app.route("/exercise", methods=["GET", "POST"])
def exercise():
    if request.method == "POST":
        activity = request.form.get("activity", "").strip()
        if activity:
            query = activity.replace(" ", "+")
            return redirect(f"https://www.google.com/search?q={query}+calories+burned")
    return render_template("exercise.html")

# -----------------------------
# RUN APP
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)
