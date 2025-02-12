from datetime import datetime
from decimal import Decimal
from dotenv import load_dotenv
from flask import Flask, jsonify, request, session
import math, os, re

app = Flask(__name__)
load_dotenv()
app.secret_key = os.getenv('SECRET_KEY', 'totally secret key')

class BaseModel:
    @staticmethod
    def validate_pattern(pattern, string):
        return bool(re.match(pattern, string))

class Receipt(BaseModel):
    def __init__(self, retailer, purchase_datetime, total, items):
        self.retailer = retailer
        self.purchase_datetime = purchase_datetime
        self.total = total
        self.items = items

    def to_dict(self):
        return {
            "retailer": self.retailer,
            "purchaseDate": f"{self.purchase_datetime.year}-{self.purchase_datetime.month:02d}-{self.purchase_datetime.day:02d}",
            "purchaseTime": f"{self.purchase_datetime.hour:02d}:{self.purchase_datetime.minute:02d}",
            "total": str(self.total),
            "items": [{'shortDescription': item.description, 'price': float(item.price)} for item in self.items]
        }
    
    @staticmethod
    def from_dict(data):
        return Receipt(
            data.get('retailer'),
            datetime.strptime(
                f"{data.get('purchaseDate')} {data.get('purchaseTime')}",
                "%Y-%m-%d %H:%M"
            ),
            Decimal(data.get('total')),
            [ Item( item.get('shortDescription').strip(), Decimal(item.get('price')) ) for item in data.get('items') ]
        )
    
    @staticmethod
    def json_keys():
        return ['retailer', 'purchaseDate', 'purchaseTime', 'total', 'items']


class Item(BaseModel):
    def __init__(self, description, price):
        self.description = description
        self.price = price

@app.before_request
def before_request():
    if 'next_id' not in session:
        session['next_id'] = "1"
    if 'receipts' not in session:
        session['receipts'] = {}

@app.route('/receipts/process', methods=['POST'])
def process_receipt():
    err_msg = "The receipt is invalid."
    if request.content_type != 'application/json':
        return jsonify(message=err_msg), 400

    data = request.json

    # Required keys
    for key in Receipt.json_keys():
        if key not in data:
            return jsonify(message=err_msg), 400
        
    money_pattern = r"^\d+\.\d{2}$"

    if Receipt.validate_pattern(money_pattern, data.get('total')) == False:
        return jsonify(message=err_msg), 400
    
    if any([Receipt.validate_pattern(money_pattern, item.get('price')) == False for item in data.get('items')]):
        return jsonify(message=err_msg), 400
    
    try:
        new_receipt = Receipt.from_dict(data)
    except ValueError:
        return jsonify(message=err_msg), 400
    
    receipt_id = session['next_id']

    session['receipts'][receipt_id] = new_receipt.to_dict()
    session['next_id'] = str( int(receipt_id) + 1 ) 

    return jsonify(id=receipt_id), 200

@app.route('/receipts/<receipt_id>/points', methods=['GET'])
def get_points(receipt_id):
    receipt_dict = session['receipts'].get(receipt_id)
    if receipt_dict:
        receipt = Receipt.from_dict(receipt_dict)
        points = 0

        # https://github.com/fetch-rewards/receipt-processor-challenge?tab=readme-ov-file#rules

        # Alphanumeric characters in retailer
        points += sum(1 for c in receipt.retailer if c.isalnum())

        # Round dollar total
        if receipt.total % Decimal('1') == 0:
            points += 50

        # Total is multiple of 0.25
        if receipt.total % Decimal('0.25') == 0:
            points += 25

        # Pairs of items
        points += ( len(receipt.items) // 2 ) * 5 

        # Length of description is multiple of 3
        for item in receipt.items:
            if len(item.description) % 3 == 0:
                points += math.ceil( item.price * Decimal('0.2') )

        # Odd purchase day
        if receipt.purchase_datetime.day % 2 != 0:
            points += 6

        # Purchase time between 2pm and 4pm exclusive
        two_pm = receipt.purchase_datetime.replace(hour=14, minute=0, second=0, microsecond=0)
        four_pm = two_pm.replace(hour=16)
        if two_pm < receipt.purchase_datetime < four_pm:
            points += 10
        return jsonify(points=points), 200
    return jsonify(message="No receipt found for that ID."), 404
