{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "bash": {
      "*": "allow"
    },
    "read": {
      "*": "allow"
    }
  },
  "mcp": {
    "banco-lia": {
      "type": "local",
      "command": [
        "uvx",
        "--from",
        "git+https://github.com/LIAUNAL/bancoProyectosPapersLIA",
        "banco-lia-mcp"
      ],
      "enabled": true
    },
    "kaggle": {
      "type": "remote",
      "url": "https://www.kaggle.com/mcp",
      "headers": {
        "Authorization": "Bearer {env:KAGGLE_API_TOKEN}"
      },
      "enabled": true
    },
    "colab": {
      "type": "local",
      "command": [
        "uvx",
        "git+https://github.com/googlecolab/colab-mcp@b9ab3899e0f1fa493390b1fd6d54aa2e464ecdf1"
      ],
      "enabled": true
    },
    "asta": {
      "type": "remote",
      "url": "https://asta-tools.allen.ai/mcp/v1",
      "headers": {
        "x-api-key": "{env:ASTA_API_KEY}"
      },
      "enabled": true
    }
  }
}
