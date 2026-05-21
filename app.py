from flask import Flask, render_template, request, redirect, session, flash, jsonify
from pymongo import MongoClient
from datetime import date, datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.security import generate_password_hash, check_password_hash
import openai
import json
import re

app = Flask(__name__)
app.secret_key = "super_secret_fitness_key"

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
users_collection = db["users"]
chat_history_collection = db["chat_history"]


today = str(date.today())
meal = meals_collection.find_one({"date": today})


# -----------------------------
# INDEX PAGE
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")

# -----------------------------
# AUTHENTICATION
# -----------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        mobile = request.form.get("mobile")
        weight = request.form.get("weight")
        height = request.form.get("height")
        username = request.form.get("username")
        password = request.form.get("password")
        
        if users_collection.find_one({"username": username}):
            flash("Username already given!", "danger")
            return redirect("/signup")
            
        hashed_pw = generate_password_hash(password)
        users_collection.insert_one({
            "name": name,
            "mobile": mobile,
            "weight": weight,
            "height": height,
            "username": username,
            "password": hashed_pw
        })
        flash(f"Account created for {name}! Please login.", "success")
        return redirect("/login")
        
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        user = users_collection.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            session["user"] = username
            return redirect("/dashboard")
        
        flash("Invalid username or password!", "danger")
        return redirect("/login")
        
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")

# -----------------------------
# DASHBOARD
# -----------------------------
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")
        
    user = session["user"]
    today_str = str(date.today())

    # --- Meal Search Logic ---
    result = None
    meal_name = ""
    searched = False

    if request.method == "POST":
        # Handle Clear Search request
        if "clear_search" in request.form:
            return redirect("/dashboard")

        if "meal_name" in request.form:
            meal_name = request.form.get("meal_name", "").strip()
            searched = True

            nutrition_data = {
                "Apple": {"calories": 52, "protein": 0.3, "fat": 0.2, "fiber": 2.4},
                "Banana": {"calories": 89, "protein": 1.1, "fat": 0.3, "fiber": 2.6},
            }
            data = get_enhanced_nutrition_data(meal_name)
            if data:
                result = {"name": meal_name.title(), **data}
            else:
                return redirect(f"https://www.google.com/search?q={meal_name}+nutrition+facts")
    
    # Fetch Stats for Sidebar
    daily = calories_collection.find_one({"date": today_str, "user": user}) or {"goal": 2000, "consumed": 0, "burned": 0}
    water = water_collection.find_one({"date": today_str, "user": user}) or {"goal": 8, "current": 0}
    
    # Calculate Remaining
    goal = daily.get("goal", 2000)
    consumed = daily.get("consumed", 0)
    burned = daily.get("burned", 0)
    remaining = max(0, goal - consumed + burned)
    
    stats = {
        "goal": goal,
        "consumed": consumed,
        "burned": burned,
        "remaining": remaining,
        "water_current": water.get("current", 0),
        "water_goal": water.get("goal", 8)
    }

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
    return render_template("dashboard.html", cards=cards, stats=stats, result=result, meal_name=meal_name, searched=searched)

# -----------------------------
# TODAY'S MEAL
# -----------------------------
@app.route("/meal")
def today_meal():
    if "user" not in session:
        return redirect("/login")
    today = str(date.today())
    user = session["user"]
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

    # Fetch Stats for Sidebar
    daily = calories_collection.find_one({"date": today, "user": user}) or {"goal": 2000, "consumed": 0, "burned": 0}
    water = water_collection.find_one({"date": today, "user": user}) or {"goal": 8, "current": 0}
    
    stats = {
        "goal": daily.get("goal", 2000),
        "consumed": daily.get("consumed", 0),
        "burned": daily.get("burned", 0),
        "remaining": max(0, daily.get("goal", 2000) - daily.get("consumed", 0) + daily.get("burned", 0)),
        "water_current": water.get("current", 0),
        "water_goal": water.get("goal", 8)
    }

    return render_template("meal.html", meal=meal, today=today, stats=stats)



# -----------------------------
# SAVE MEAL
# -----------------------------
@app.route("/meal/save", methods=["POST"])
def save_meal():
    if "user" not in session: return redirect("/login")
    today = str(date.today())
    user = session["user"]
    meal_data = {
        "date": today,
        "user": user,
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
        {"date": today, "user": user},
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
# GPT NUTRITION SEARCH (FALLBACK)
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
# ENHANCED NUTRITION SEARCH WITH CHAT
# -----------------------------
def get_enhanced_nutrition_data(food_name):
    """Enhanced nutrition search with more comprehensive database"""
    
    # Expanded nutrition database
    nutrition_database = {
        # Fruits
        "apple": {"calories": 52, "protein": 0.3, "fat": 0.2, "fiber": 2.4, "carbs": 14},
        "banana": {"calories": 89, "protein": 1.1, "fat": 0.3, "fiber": 2.6, "carbs": 23},
        "orange": {"calories": 47, "protein": 0.9, "fat": 0.1, "fiber": 2.4, "carbs": 12},
        "grapes": {"calories": 62, "protein": 0.6, "fat": 0.2, "fiber": 0.9, "carbs": 16},
        "strawberry": {"calories": 32, "protein": 0.7, "fat": 0.3, "fiber": 2.0, "carbs": 8},
        "mango": {"calories": 60, "protein": 0.8, "fat": 0.4, "fiber": 1.6, "carbs": 15},
        "pineapple": {"calories": 50, "protein": 0.5, "fat": 0.1, "fiber": 1.4, "carbs": 13},
        
        # Vegetables
        "broccoli": {"calories": 34, "protein": 2.8, "fat": 0.4, "fiber": 2.6, "carbs": 7},
        "spinach": {"calories": 23, "protein": 2.9, "fat": 0.4, "fiber": 2.2, "carbs": 4},
        "carrot": {"calories": 41, "protein": 0.9, "fat": 0.2, "fiber": 2.8, "carbs": 10},
        "tomato": {"calories": 18, "protein": 0.9, "fat": 0.2, "fiber": 1.2, "carbs": 4},
        "cucumber": {"calories": 16, "protein": 0.7, "fat": 0.1, "fiber": 0.5, "carbs": 4},
        "lettuce": {"calories": 15, "protein": 1.4, "fat": 0.2, "fiber": 1.3, "carbs": 3},
        
        # Grains & Cereals
        "rice": {"calories": 130, "protein": 2.7, "fat": 0.3, "fiber": 0.4, "carbs": 28},
        "bread": {"calories": 265, "protein": 9.0, "fat": 3.2, "fiber": 2.7, "carbs": 49},
        "oats": {"calories": 389, "protein": 16.9, "fat": 6.9, "fiber": 10.6, "carbs": 66},
        "quinoa": {"calories": 368, "protein": 14.1, "fat": 6.1, "fiber": 7.0, "carbs": 64},
        
        # Proteins
        "chicken": {"calories": 239, "protein": 27.3, "fat": 13.6, "fiber": 0, "carbs": 0},
        "egg": {"calories": 155, "protein": 13.0, "fat": 11.0, "fiber": 0, "carbs": 1.1},
        "fish": {"calories": 206, "protein": 22.0, "fat": 12.0, "fiber": 0, "carbs": 0},
        "beef": {"calories": 250, "protein": 26.0, "fat": 15.0, "fiber": 0, "carbs": 0},
        "tofu": {"calories": 76, "protein": 8.0, "fat": 4.8, "fiber": 0.3, "carbs": 1.9},
        
        # Dairy
        "milk": {"calories": 42, "protein": 3.4, "fat": 1.0, "fiber": 0, "carbs": 5.0},
        "yogurt": {"calories": 59, "protein": 10.0, "fat": 0.4, "fiber": 0, "carbs": 3.6},
        "cheese": {"calories": 113, "protein": 7.0, "fat": 9.0, "fiber": 0, "carbs": 1.0},
        
        # Nuts & Seeds
        "almonds": {"calories": 579, "protein": 21.2, "fat": 49.9, "fiber": 12.5, "carbs": 22},
        "walnuts": {"calories": 654, "protein": 15.2, "fat": 65.2, "fiber": 6.7, "carbs": 14},
        "peanuts": {"calories": 567, "protein": 25.8, "fat": 49.2, "fiber": 8.5, "carbs": 16},
        
        # Common Indian Foods
        "roti": {"calories": 297, "protein": 11.0, "fat": 4.0, "fiber": 11.0, "carbs": 61},
        "dal": {"calories": 116, "protein": 9.0, "fat": 0.4, "fiber": 8.0, "carbs": 20},
        "rajma": {"calories": 127, "protein": 8.7, "fat": 0.5, "fiber": 6.4, "carbs": 23},
        "paneer": {"calories": 265, "protein": 18.3, "fat": 20.8, "fiber": 0, "carbs": 1.2},
    }
    
    # Clean and normalize the food name
    food_name = food_name.lower().strip()
    
    # Direct match
    if food_name in nutrition_database:
        return nutrition_database[food_name]
    
    # Partial match
    for key in nutrition_database:
        if food_name in key or key in food_name:
            return nutrition_database[key]
    
    # Try GPT if available
    return get_nutrition_from_gpt(food_name)

def extract_food_name_from_message(message):
    """Extract food name from natural language message"""
    message = message.lower().strip()
    
    # Common patterns to extract food names
    patterns = [
        r"nutrition (?:facts )?(?:for |of |about )?(.+)",
        r"(?:what (?:are )?(?:the )?)?nutrition (?:facts )?(?:for |of |about )?(.+)",
        r"tell me about (.+) nutrition",
        r"(.+) nutrition (?:facts|info|information)",
        r"calories in (.+)",
        r"(?:what (?:are )?(?:the )?)?(?:nutritional )?(?:value|values|info|information) (?:for |of |about )?(.+)",
        r"(?:how many )?calories (?:does |in |are in )?(.+)(?: have| contain)?",
        r"(.+) (?:calories|nutrition|nutritional facts)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            food_name = match.group(1).strip()
            # Clean up common words
            food_name = re.sub(r'\b(?:a|an|the|some|any|per|100g|100 grams?|one|1)\b', '', food_name).strip()
            return food_name
    
    # If no pattern matches, assume the whole message is a food name
    return message

# -----------------------------
# CHAT ENDPOINT FOR MEAL SEARCH
# -----------------------------
@app.route("/chat/meal-search", methods=["POST"])
def chat_meal_search():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user = session["user"]
    data = request.get_json()
    message = data.get("message", "").strip()
    
    if not message:
        return jsonify({"response": "Please ask me about a specific food item!"})
    
    # Extract food name from the message
    food_name = extract_food_name_from_message(message)
    
    if not food_name:
        return jsonify({
            "response": "I couldn't understand which food you're asking about. Please try asking like 'What are the nutrition facts for apple?' or 'Tell me about banana nutrition'."
        })
    
    # Get nutrition data
    nutrition_data = get_enhanced_nutrition_data(food_name)
    
    if nutrition_data:
        # Save chat to database
        chat_entry = {
            "user": user,
            "timestamp": datetime.now(),
            "user_message": message,
            "food_name": food_name.title(),
            "nutrition_data": nutrition_data,
            "date": str(date.today())
        }
        chat_history_collection.insert_one(chat_entry)
        
        response_text = f"Here are the nutrition facts for {food_name.title()}:"
        
        return jsonify({
            "response": response_text,
            "nutrition": {
                "name": food_name.title(),
                **nutrition_data
            }
        })
    else:
        # Save failed search to database
        chat_entry = {
            "user": user,
            "timestamp": datetime.now(),
            "user_message": message,
            "food_name": food_name.title(),
            "nutrition_data": None,
            "date": str(date.today())
        }
        chat_history_collection.insert_one(chat_entry)
        
        return jsonify({
            "response": f"I don't have nutrition information for '{food_name.title()}' in my database. You can try searching online or asking about other common foods like fruits, vegetables, grains, or proteins."
        })

# -----------------------------
# GET CHAT HISTORY
# -----------------------------
@app.route("/chat/history", methods=["GET"])
def get_chat_history():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user = session["user"]
    today_str = str(date.today())
    
    # Get today's chat history
    history = list(chat_history_collection.find(
        {"user": user, "date": today_str},
        {"_id": 0}
    ).sort("timestamp", 1))
    
    return jsonify({"history": history})

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
    if "user" not in session: return redirect("/login")
    today = str(date.today())
    user = session["user"]

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
    if "user" not in session: return redirect("/login")
    today = str(date.today())
    user = session["user"]

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

        # REMOVE ONE GLASS
        if "remove_water" in request.form:
            if water_data["current"] > 0:
                water_data["current"] -= 1

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
    if "user" not in session: return redirect("/login")
    today = str(date.today())
    user = session["user"]

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
    if "user" not in session: return redirect("/login")
    user = session["user"]
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
    if "user" not in session: return redirect("/login")
    today = str(date.today())
    user = session["user"]

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
