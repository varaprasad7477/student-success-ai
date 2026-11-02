# Demonstration Walkthrough

## Best route for a final presentation

Use the **development demonstration** button. It does not require an email or password and uses public benchmark data only.

1. Open `http://127.0.0.1:8000`.
2. Click **Explore development demonstration**.
3. Open **Try a test CSV** from the sidebar.
4. Download `simple_college_demo_60.csv` from the Sample files panel.
5. Upload that same file.
6. Confirm the mapping below, then click **Confirm mapping and check data**.
7. Click **Open overview**.
8. Open **Review a student** and select a student record.
9. Explain the plain-English observations and suggested support conversation.
10. Open **About this model** and explain that a review group is not a dropout verdict.

## Mapping for the simple CSV

| CSV header | Choose this meaning in the app | Why it is needed |
|---|---|---|
| `Student ID` | Student identifier | Finds one unique student record. Required. |
| `Attendance %` | Attendance rate | Shows whether attendance has reduced. The app converts percentages such as 75 to 0.75. |
| `Assignments Due` | Assignments due | Number of expected tasks. |
| `Assignments Submitted` | Assignments submitted / evaluated | Used with expected tasks to calculate work completion. |
| `Average Mark` | Assessment average | Current academic result out of 100. |
| `Days Since Login` | Days since last login | Identifies a gap in recorded platform activity. |
| `Credits Completed %` | Credits completed ratio | Academic progress. The app converts percentages such as 50 to 0.50. |
| `Academic Engagement` | Engagement score | A 0–1 activity measure. |
| `Historical Outcome` | Do not map | A demo-only past outcome label for discussion. It must not be used to score the current record. |

## How to explain the result

Say: “The system groups records into low, medium, or high review priority using the available learning data. It does not know a student’s personal reason for struggling. The teacher verifies the record, speaks with the student, and agrees a useful support action.”

## How a new university signs up

1. On the sign-in page, choose **Create an institution workspace**.
2. Enter the institution name, type, current term, data owner, and review horizon.
3. Select only learning signals that exist before the chosen review date.
4. Create the administrator account.
5. Sign in and open **Data setup**.
6. Upload a small CSV first and confirm its column meanings in **Try a test CSV**.
7. Until the university trains and validates its own historical model, use the workspace for data checking, local support rules, and human review only.
