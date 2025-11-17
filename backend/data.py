import pandas

TIMESTAMP_KEY = 'TIMESTAMP'
RED_KEY = 'RED'
IR_KEY = 'IR'
GREEN_KEY = 'GREEN'
DELTA_END = '_DELTA'

def ppg_dict_to_dataframe(ppg_dict: dict) -> pandas.DataFrame:
    """Converts a PPG data dictionary to a pandas DataFrame."""

    def deltas_to_values(deltas: list[int]) -> list[int]:
        """Converts a list in delta format to absolute format."""
        if not deltas:
            return deltas

        values = [deltas[0]]
        for delta in deltas[1:]:
            values.append(values[-1] + delta)

        return values

    # Determine if the data is in delta format or invalid.
    is_delta_format = False
    if ppg_dict.get(TIMESTAMP_KEY) is None:
        if ppg_dict.get(TIMESTAMP_KEY + DELTA_END):
            is_delta_format = True
        else:
            raise ValueError("No timestamp data found in dictionary.")

    # Prepare keys based on format.
    timestamp_key = TIMESTAMP_KEY + (DELTA_END if is_delta_format else '')
    red_key = RED_KEY + (DELTA_END if is_delta_format else '')
    ir_key = IR_KEY + (DELTA_END if is_delta_format else '')
    green_key = GREEN_KEY + (DELTA_END if is_delta_format else '')

    # Extract data from the dictionary.
    new_dict = {
                key.split('_')[0]: ppg_dict.get(key, [])
                        for key in [timestamp_key, red_key, ir_key, green_key]
            }

    # Convert from delta format to absolute values if necessary.
    if is_delta_format:
        for key in new_dict:
            deltas = new_dict[key]
            new_dict[key] = deltas_to_values(deltas)

    index = new_dict.pop(TIMESTAMP_KEY)
    return pandas.DataFrame(new_dict, index=index)

def store_ppg_dataframe_to_csv(folder: str, prefix: str, df: pandas.DataFrame) -> str:
    """Stores the PPG DataFrame to a CSV file and returns the file path."""
    import os
    import datetime

    if not os.path.exists(folder):
        os.makedirs(folder)

    filename = f"{prefix}_ppg.csv"
    filepath = os.path.join(folder, filename)

    df.to_csv(filepath)
    return filepath
