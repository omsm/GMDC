from flask import *

app = Flask(__name__)

@app.route("/")
def home():
    return {"message": "Hello, World!"}

@app.route("/read_stable_weight", methods=["POST"])
def read_stable_weight():
    # return {"weight": 44970.0} # Gross
    # return {"weight": 25950} # Tare
    return {"weight": 44970} # Vadhghat

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=True)